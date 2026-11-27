using System;
using System.Collections.Generic;
using System.Linq;
using System.Text;
using nadena.dev.modular_avatar.core;
using UnityEditor;
using UnityEditor.Animations;
using UnityEngine;
using VRC.Dynamics;
using Wirenook.AdventureTools.Core;
using Wirenook.AdventureTools.Editor;
using Wirenook.Assets;
using Wirenook.SelectiveAnimation.Core;
using Wirenook.SkillChecks;
using Wirenook.SkillChecks.Avatar.Editor;
using Wirenook.WorldSync.Core;
using Wirenook.WorldSync.Editor;
using Client = Wirenook.WorldSync.Editor.AnchorBusCheck.Client;

namespace Wirenook.Meta.Crypt.Editor
{
    /// <summary>
    /// Runs the crypt's kit in the editor, as far as the editor can, the
    /// way the plain kit's own check does: the generated animator is
    /// played on copies of the prefab, one for the wearer's client and one
    /// each for someone backstage and a stranger, with parameter drivers
    /// carried out and the synced parameters copied across ten times a
    /// second. No contact is real here: what a contact receiver would
    /// report is written into each client's animator.
    ///
    /// What it proves is the state machines and their timing: who is shown
    /// the course before and after it goes live and where its contacts are
    /// on, how the barricade comes down under hands and under fire, that
    /// the chest opens only once the key is taken, that the danger zone
    /// warns for as long as it says before it strikes, that the rift
    /// seals, creeps open and stays shut, that the pendulum swings in step
    /// for a viewer and for someone who arrives part way through, over a
    /// network that is late by a different amount each time, and that a
    /// value on the bus reaches a viewer. It cannot prove that VRChat's contacts, stencils
    /// or drivers behave as stood in for; none of this has run in a
    /// client.
    /// </summary>
    public static class CryptCheck
    {
        private const string Prefix = "GM";
        private const string StagePrefix = Prefix + "/Stage";
        private const string BusPrefix = StagePrefix + "/Bus";
        private const string CryptPrefix = Prefix + "/Crypt";
        private const string Live = StagePrefix + "/Live";
        private const float Step = AnchorBusCheck.Step;
        private const float NetworkSeconds = 0.1f;

        private static string On(string thing) => StagePrefix + "/" + thing.Replace(" ", "");

        /// <summary>Three clients and the network between them.</summary>
        private sealed class Table : IDisposable
        {
            public readonly Client Wearer;
            public readonly Client Backstage;
            public readonly Client Stranger;
            public readonly Dictionary<string, int> Slots;
            private readonly WorldGrid _grid = new WorldGrid(512f);
            private float _sinceSync;

            public Table(GameObject prefab, AnimatorController controller, Dictionary<string, int> slots, List<string> synced)
            {
                Slots = slots;
                Wearer = new Client(prefab, controller, BusPrefix, true, false);
                Backstage = new Client(prefab, controller, BusPrefix, false, false);
                Stranger = new Client(prefab, controller, BusPrefix, false, false);
                Backstage.Animator.SetBool(CircleNames.Seen(PresenceModel.BackstageCircle), true);
                foreach (var client in All) client.AlsoSynced.AddRange(synced);
            }

            public IEnumerable<Client> All => new[] { Wearer, Backstage, Stranger };
            public IEnumerable<Client> Others => new[] { Backstage, Stranger };

            public void Frame()
            {
                Wearer.Advance(_grid);
                _sinceSync += Step;
                var arrives = _sinceSync >= NetworkSeconds;
                if (arrives) _sinceSync = 0f;
                foreach (var other in Others)
                {
                    if (arrives) other.Receive(Wearer);
                    other.Ease(false);
                    other.Advance(_grid);
                }
            }

            public void Run(float seconds, Action eachFrame = null)
            {
                for (var elapsed = 0f; elapsed < seconds; elapsed += Step)
                {
                    Frame();
                    eachFrame?.Invoke();
                }
            }

            /// <summary>Stands a thing where it is, for everyone, without going through the setting down (the plain kit's check covers that).</summary>
            public void Stand(string thing, bool standing)
            {
                foreach (var client in All) client.Animator.SetBool(BusPrefix + "/" + Slots[thing] + "/Set", standing);
                Wearer.Animator.SetBool(On(thing), standing);
            }

            public void GoLive(bool live) => Wearer.Animator.SetBool(Live, live);

            public void Dispose()
            {
                foreach (var client in All) client.Dispose();
            }
        }

        private static Transform At(Client client, string path)
        {
            var found = client.Instance.transform.Find(path);
            if (found == null) throw new InvalidOperationException("The kit has no object at " + path + ".");
            return found;
        }

        /// <summary>How large something is drawn, as a share of its modelled size.</summary>
        private static float Size(Client client, string path)
        {
            return At(client, path).lossyScale.x / Mathf.Max(client.Instance.transform.lossyScale.x, 1e-6f);
        }

        private static bool Active(Client client, string path) => At(client, path).gameObject.activeInHierarchy;

        private static float Material(Client client, string renderer, string property)
        {
            var block = new MaterialPropertyBlock();
            At(client, renderer).GetComponent<SkinnedMeshRenderer>().GetPropertyBlock(block);
            return block.HasFloat(property) ? block.GetFloat(property) : 0f;
        }

        private static float Shape(Client client, string shape)
        {
            var renderer = At(client, CryptSet.SolidName).GetComponent<SkinnedMeshRenderer>();
            var index = renderer.sharedMesh.GetBlendShapeIndex(shape);
            if (index < 0) throw new InvalidOperationException(CryptSet.SolidName + " has no blendshape " + shape + ".");
            return renderer.GetBlendShapeWeight(index);
        }

        private static bool In(Client client, AnimatorController controller, string layer, string state)
        {
            var index = Array.FindIndex(controller.layers, candidate => candidate.name == layer);
            if (index < 0) throw new InvalidOperationException("The kit has no layer called " + layer + ".");
            return client.Animator.GetCurrentAnimatorStateInfo(index).IsName(state);
        }

        private static AvatarCheck Named(string name) => new AvatarCheck(name, new CheckSpec());

        /// <returns>A report ending in "ok" or listing what failed.</returns>
        public static string Run()
        {
            var problems = new List<string>();
            var text = new StringBuilder();
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(CryptBuild.KitPrefab);
            var controller = AssetDatabase.LoadAssetAtPath<AnimatorController>(CryptBuild.KitController);
            if (prefab == null || controller == null) return "FAILED\n  missing " + CryptBuild.KitPrefab + " or " + CryptBuild.KitController;

            var plan = new StagePlan();
            foreach (var tool in CryptBuild.Tools()) tool.Things(plan);
            var slots = plan.Things.Select((thing, index) => (thing.name, slot: index + 1)).ToDictionary(pair => pair.name, pair => pair.slot);

            var bus = AnchorBusCheck.Run(CryptBuild.KitPrefab, CryptBuild.KitController, BusPrefix, slots.Count,
                StagePrefix + "/Place", StagePrefix + "/Clear", StagePrefix + "/Air");
            text.AppendLine("The bus, with a value for each of its " + slots.Count + " slots:");
            foreach (var line in bus.TrimEnd().Split('\n')) text.AppendLine("  " + line.TrimEnd());
            if (!bus.TrimEnd().EndsWith("ok", StringComparison.Ordinal)) problems.Add("The bus fails its own check.");

            var declared = prefab.GetComponentsInChildren<ModularAvatarParameters>(true).SelectMany(component => component.parameters).ToList();
            var synced = declared.Where(parameter => !parameter.localOnly && parameter.syncType != ParameterSyncType.NotSynced)
                .Select(parameter => parameter.nameOrPrefix).Where(name => !name.StartsWith(BusPrefix + "/", StringComparison.Ordinal))
                // What the kit carries beside itself (the notices) has an animator of its own.
                .Where(name => controller.parameters.Any(parameter => parameter.name == name)).Distinct().ToList();

            Structure(prefab, declared, plan, text, problems);
            Table Seat() => new Table(prefab, controller, slots, synced);
            using (var table = Seat()) Rehearsal(table, text, problems);
            using (var table = Seat()) Barricade(table, text, problems);
            using (var table = Seat()) Chest(table, controller, text, problems);
            using (var table = Seat()) Danger(table, text, problems);
            using (var table = Seat()) Pendulum(table, prefab, controller, synced, text, problems);
            using (var table = Seat()) Rift(table, controller, text, problems);
            using (var table = Seat()) Values(table, text, problems);
            return text + (problems.Count == 0 ? "ok" : "FAILED\n  " + string.Join("\n  ", problems.Distinct()));
        }

        /// <summary>What the prefab carries, counted, and what the saving on the bus comes to.</summary>
        private static void Structure(GameObject prefab, List<ParameterConfig> declared, StagePlan plan, StringBuilder text, List<string> problems)
        {
            int Bits(IEnumerable<ParameterConfig> parameters) => parameters
                .Where(parameter => !parameter.localOnly && parameter.syncType != ParameterSyncType.NotSynced)
                .GroupBy(parameter => parameter.nameOrPrefix).Select(group => group.First())
                .Sum(parameter => parameter.syncType == ParameterSyncType.Bool ? 1 : 8);

            var contacts = prefab.GetComponentsInChildren<ContactBase>(true);
            var counted = contacts.Count(contact => !contact.localOnly);
            var sources = prefab.GetComponentsInChildren<AudioSource>(true).Length;
            var constraints = prefab.GetComponentsInChildren<VRCConstraintBase>(true).Length;
            var meshes = prefab.GetComponentsInChildren<SkinnedMeshRenderer>(true);
            var bits = Bits(declared);
            text.AppendLine("Carries: " + bits + " synced bits, " + counted + " contacts that count (" + (contacts.Length - counted) +
                            " local-only), " + sources + " audio sources, " + constraints + " constraints, " + meshes.Length + " meshes with " +
                            meshes.Sum(mesh => mesh.sharedMaterials.Length) + " material slots and " +
                            meshes.Sum(mesh => mesh.sharedMesh.triangles.Length / 3) + " triangles");
            foreach (var mesh in meshes)
                text.AppendLine("  " + mesh.name + ": " + mesh.sharedMesh.triangles.Length / 3 + " triangles in " + mesh.sharedMaterials.Length + " slots");

            // What riding the bus saves: a synced float each would be eight bits a thing.
            var things = plan.Things.Count;
            text.AppendLine("Values: " + things + " things each have one, for " + AnchorBus.ValueBits + " synced bits between them; a synced float each would be " +
                            things * 8 + ". The dials that use one: " + Dials(plan) + ".");

            // Very Poor begins past these, on PC.
            if (sources > 8) problems.Add("The kit alone has " + sources + " audio sources; an avatar with more than eight is Very Poor.");
            if (counted > 32) problems.Add("The kit alone has " + counted + " contacts that count; an avatar with more than thirty-two is Very Poor.");
            if (bits > 256) problems.Add("The kit syncs " + bits + " bits; an avatar may sync 256.");

            foreach (var name in new[] { CryptSet.SolidName, CryptSet.EffectsName })
            {
                var holder = prefab.transform.Find(name);
                if (holder == null || holder.GetComponent<WirenookApart>() == null)
                    problems.Add(name + " is not marked as standing apart from the wearer's figure.");
            }

            var effects = prefab.transform.Find(CryptSet.EffectsName);
            if (effects != null && effects.GetComponent<WirenookPcOnly>() == null)
                problems.Add(CryptSet.EffectsName + " is drawn with shaders that mobile builds may not use and is not marked PC-only.");

            // Every contact of the crypt's rests switched off: it is the animator that says where a thing is real.
            foreach (var contact in contacts.Where(contact => !contact.localOnly))
            {
                var path = AnimationUtility.CalculateTransformPath(contact.transform, prefab.transform);
                var crypt = plan.Things.Where(thing => thing.rehearsed).Any(thing => path.StartsWith("Stage/" + thing.name + "/", StringComparison.Ordinal));
                if (crypt && contact.gameObject.activeInHierarchy)
                    problems.Add("The contact at " + path + " rests switched on: it would act on people before the course is live.");
                if (contact.radius * contact.transform.lossyScale.x > 3.001f)
                    problems.Add("The contact at " + path + " is larger than VRChat allows a contact to be.");
            }
        }

        private static string Dials(StagePlan plan)
        {
            var sized = plan.Things.Count(thing => thing.name.StartsWith("Zone ", StringComparison.Ordinal) || thing.name == PauseTool.ThingName ||
                                                   thing.name.EndsWith(" Zone", StringComparison.Ordinal) || thing.name == DangerPiece.ThingName);
            var turned = new[] { BarricadePiece.ThingName, ChestPiece.ChestName, PendulumPiece.ThingName, RiftPiece.ThingName }.Count(name => plan.Things.Any(thing => thing.name == name));
            return sized + " sizes and " + turned + " headings";
        }

        /// <summary>Who is shown the course before it is live and after, how it is drawn for them, and where its contacts are on.</summary>
        private static void Rehearsal(Table table, StringBuilder text, List<string> problems)
        {
            const string bone = "Stage/" + BarricadePiece.ThingName;
            const string contacts = bone + "/Turn/Contacts";
            var who = new[] { (client: table.Wearer, name: "the wearer"), (client: table.Backstage, name: "someone backstage"), (client: table.Stranger, name: "a stranger") };
            var cases = 0;

            void Expect(string when, bool wearer, bool backstage, bool stranger, bool spectral, bool touchable)
            {
                var shown = new[] { wearer, backstage, stranger };
                for (var index = 0; index < who.Length; index++)
                {
                    cases++;
                    var size = Size(who[index].client, bone);
                    if (shown[index] ? size < 0.5f : size > 0.01f)
                        problems.Add(when + ": " + who[index].name + (shown[index] ? " is not shown the barricade." : " is shown the barricade."));
                    if (shown[index] && Material(who[index].client, CryptSet.SolidName, "_WirenookSpectral") > 0.5f != spectral)
                        problems.Add(when + ": " + who[index].name + " sees the barricade " + (spectral ? "solid; it should be a spectre." : "as a spectre; it should be solid."));
                    if (Active(who[index].client, contacts) != touchable)
                        problems.Add(when + ": on the client of " + who[index].name + " the barricade's contact is " + (touchable ? "off." : "on."));
                }
            }

            table.Run(0.5f);
            Expect("Before anything is set out", false, false, false, false, false);
            table.Stand(BarricadePiece.ThingName, true);
            table.Run(1f);
            Expect("Set out, not live", true, true, false, true, false);
            table.GoLive(true);
            table.Run(1f);
            Expect("Live", true, true, true, false, true);
            table.GoLive(false);
            table.Run(1f);
            Expect("Taken back behind the scenes", true, true, false, true, false);

            // The wearer, carrying a thing about before it stands anywhere: theirs alone.
            table.Stand(BarricadePiece.ThingName, false);
            table.Wearer.Animator.SetInteger(StagePrefix + "/Aim", table.Slots[BarricadePiece.ThingName]);
            table.Run(1f);
            Expect("Aimed, not yet set down", true, false, false, true, false);
            table.Wearer.Animator.SetInteger(StagePrefix + "/Aim", 0);
            text.AppendLine("Rehearsal: " + cases + " cases of who is shown the course, how, and where it can be touched");
        }

        /// <summary>The barricade under hands, let go of, under fire, down, and set out again.</summary>
        private static void Barricade(Table table, StringBuilder text, List<string> problems)
        {
            var check = Named("crypt-barricade");
            const string flames = "Stage/" + BarricadePiece.ThingName + "/Turn/Flames";
            int Down(Client client) => Enumerable.Range(1, BarricadePiece.Planks).Count(plank => Shape(client, BarricadePiece.Plank(plank)) > 99f);
            void Touch(string tag, bool touching)
            {
                // The stranger stands too far off to be shown the contact at all.
                foreach (var client in new[] { table.Wearer, table.Backstage }) client.Animator.SetFloat(check.Touching(tag), touching ? 1f : 0f);
            }

            table.Stand(BarricadePiece.ThingName, true);
            table.GoLive(true);
            table.Run(1f);
            if (Down(table.Wearer) != 0) problems.Add("The barricade is set out with " + Down(table.Wearer) + " planks already off.");

            Touch(SkillTags.Hand, true);
            table.Run(BarricadePiece.TakesSeconds * 0.45f);
            Touch(SkillTags.Hand, false);
            var progress = table.Wearer.Animator.GetFloat(check.Progress);
            var expected = SkillClock.Extrapolate(0f, 1f / BarricadePiece.TakesSeconds, 0.0, BarricadePiece.TakesSeconds * 0.45f);
            if (Mathf.Abs(progress - expected) > 0.03f)
                problems.Add("After " + (BarricadePiece.TakesSeconds * 0.45f) + " s of hands the barricade is " + progress.ToString("0.00") + " undone; the check's rules say " + expected.ToString("0.00") + ".");
            if (Down(table.Wearer) != 2) problems.Add("At " + progress.ToString("0.00") + " undone the barricade has lost " + Down(table.Wearer) + " planks; it should have lost 2.");

            table.Run(3f);
            var kept = table.Wearer.Animator.GetFloat(check.Progress);
            if (Mathf.Abs(kept - progress) > 0.01f) problems.Add("Let go of, the barricade went from " + progress.ToString("0.00") + " to " + kept.ToString("0.00") + " undone; it should keep what was done.");

            Touch(SkillTags.Fire, true);
            table.Run(1f);
            if (Size(table.Wearer, flames) < 0.5f) problems.Add("Fire on the barricade shows no flames.");
            if (Size(table.Stranger, flames) > 0.01f) problems.Add("A stranger whose client reports no fire is shown flames on the barricade.");
            var seconds = 1f;
            while (seconds < BarricadePiece.TakesSeconds && !table.Wearer.Animator.GetBool(check.Done))
            {
                table.Frame();
                seconds += Step;
            }

            var took = BarricadePiece.TakesSeconds * 0.45f + seconds;
            if (!table.Wearer.Animator.GetBool(check.Done) || Mathf.Abs(took - BarricadePiece.TakesSeconds) > 0.4f)
                problems.Add("The barricade was down after " + took.ToString("0.0") + " s of touching; it should take " + BarricadePiece.TakesSeconds + ".");
            table.Run(0.6f);
            Touch(SkillTags.Fire, false);
            table.Run(0.6f);
            foreach (var (client, name) in new[] { (table.Wearer, "the wearer"), (table.Backstage, "someone backstage"), (table.Stranger, "a stranger who saw no contact") })
            {
                if (Down(client) != BarricadePiece.Planks) problems.Add("With the barricade down, " + name + " still sees " + (BarricadePiece.Planks - Down(client)) + " planks.");
                if (Size(client, flames) > 0.01f) problems.Add("With the barricade down, " + name + " still sees it burning.");
            }

            table.Run(4f);
            if (Down(table.Wearer) != BarricadePiece.Planks) problems.Add("The barricade put itself back up.");

            table.Wearer.Animator.SetBool(On(BarricadePiece.ThingName), false);
            table.Run(0.8f);
            table.Wearer.Animator.SetBool(On(BarricadePiece.ThingName), true);
            table.Run(1f);
            foreach (var client in table.All)
                if (Down(client) != 0)
                    problems.Add("Taken away and set out again, the barricade is still missing " + Down(client) + " planks for someone.");
            text.AppendLine("Barricade: two planks off after " + (BarricadePiece.TakesSeconds * 0.45f) + " s of hands, kept when let go, down after " + took.ToString("0.0") +
                            " s in all with fire finishing it, for a stranger too; whole again when set out again");
        }

        /// <summary>The chest: a hand without the key, the key, a hand with it.</summary>
        private static void Chest(Table table, AnimatorController controller, StringBuilder text, List<string> problems)
        {
            var found = Named("crypt-found");
            var opened = Named("crypt-opened");
            const string lid = "Stage/" + ChestPiece.ChestName + "/Turn/Lid";
            const string key = "Stage/" + ChestPiece.KeyName + "/Bob";
            void Touch(AvatarCheck check, bool touching)
            {
                foreach (var client in new[] { table.Wearer, table.Backstage }) client.Animator.SetFloat(check.Touching(SkillTags.Hand), touching ? 1f : 0f);
            }

            float Lid(Client client) => Mathf.DeltaAngle(0f, At(client, lid).localEulerAngles.x);

            table.Stand(ChestPiece.ChestName, true);
            table.Stand(ChestPiece.KeyName, true);
            table.GoLive(true);
            table.Run(1f);

            var rattles = 0;
            var rattling = false;
            Touch(opened, true);
            table.Run(2.5f, () =>
            {
                var now = In(table.Wearer, controller, "Chest Padlock", "Rattle");
                if (now && !rattling) rattles++;
                rattling = now;
            });
            if (table.Wearer.Animator.GetFloat(opened.Progress) > 0.01f || Mathf.Abs(Lid(table.Wearer)) > 1f)
                problems.Add("A hand on the padlock began to open the chest before the key was taken.");
            if (rattles != 1) problems.Add("A hand held on the locked padlock rattled it " + rattles + " times; once for each time a hand comes to it.");
            Touch(opened, false);
            table.Run(0.5f);

            Touch(found, true);
            table.Run(0.8f);
            Touch(found, false);
            table.Run(0.6f);
            if (!table.Wearer.Animator.GetBool(found.Done)) problems.Add("A hand on the key for 0.8 s did not take it.");
            foreach (var (client, name) in new[] { (table.Wearer, "the wearer"), (table.Stranger, "a stranger who saw no contact") })
                if (Size(client, key) > 0.02f)
                    problems.Add("The key was taken and " + name + " still sees it lying there.");
            table.Run(2f);
            if (!table.Wearer.Animator.GetBool(found.Done)) problems.Add("The key, once taken, came back.");

            Touch(opened, true);
            table.Run(1.2f);
            Touch(opened, false);
            table.Run(0.8f);
            if (!table.Wearer.Animator.GetBool(opened.Done)) problems.Add("A hand on the padlock with the key taken did not open the chest.");
            foreach (var (client, name) in new[] { (table.Wearer, "the wearer"), (table.Stranger, "a stranger who saw no contact") })
                if (Lid(client) > -70f)
                    problems.Add("The chest is open and " + name + " sees its lid at " + Lid(client).ToString("0") + " degrees.");
            if (!In(table.Wearer, controller, "Chest Padlock", "Open")) problems.Add("The padlock did not give when the chest opened.");
            text.AppendLine("Chest: shut to a hand without the key (one rattle), the key taken in under a second and gone for everyone, then open to a hand");
        }

        /// <summary>The danger zone: how long it warns, how long it strikes, and that it does neither behind the scenes.</summary>
        private static void Danger(Table table, StringBuilder text, List<string> problems)
        {
            const string size = "Stage/" + DangerPiece.ThingName + "/Size";
            const string fill = size + "/Fill";
            const string hit = size + "/Hit";
            var striking = DangerPiece.Striking(CryptPrefix);
            var once = DangerPiece.Once(CryptPrefix);

            // What one viewer sees over a stretch of time: when the warning began, when the strike began and ended, and how many strikes.
            (float warned, float struck, float over, int strikes) Watch(Client client, float seconds, Action<float> meanwhile = null)
            {
                float warned = -1f, struck = -1f, over = -1f;
                var strikes = 0;
                var hitting = false;
                var elapsed = 0f;
                table.Run(seconds, () =>
                {
                    elapsed += Step;
                    meanwhile?.Invoke(elapsed);
                    if (warned < 0f && Size(client, fill) > 0.03f) warned = elapsed;
                    var now = Active(client, hit);
                    if (now && !hitting)
                    {
                        strikes++;
                        if (struck < 0f) struck = elapsed;
                    }

                    if (!now && hitting && over < 0f) over = elapsed;
                    hitting = now;
                });
                return (warned, struck, over, strikes);
            }

            table.Stand(DangerPiece.ThingName, true);
            table.Run(1f);
            table.Wearer.Animator.SetBool(striking, true);
            var hidden = Watch(table.Backstage, 4f);
            if (hidden.strikes > 0 || hidden.warned >= 0f) problems.Add("The danger zone warned or struck while the course was still behind the scenes.");
            table.Wearer.Animator.SetBool(striking, false);
            table.GoLive(true);
            table.Run(1f);

            // A press of the menu's button, a fifth of a second long.
            table.Wearer.Animator.SetBool(once, true);
            var seen = Watch(table.Stranger, 6f, elapsed =>
            {
                if (elapsed >= 0.2f) table.Wearer.Animator.SetBool(once, false);
            });
            if (seen.strikes != 1) problems.Add("\"Strike once\" struck " + seen.strikes + " times for a stranger.");
            else
            {
                var warning = seen.struck - seen.warned;
                var blow = seen.over - seen.struck;
                if (Mathf.Abs(warning - DangerPiece.TelegraphSeconds) > 0.15f)
                    problems.Add("The danger zone warned for " + warning.ToString("0.00") + " s before it struck; it should be " + DangerPiece.TelegraphSeconds + ".");
                if (Mathf.Abs(blow - DangerPiece.HitSeconds) > 0.08f)
                    problems.Add("The danger zone's strike lasted " + blow.ToString("0.00") + " s; it should be " + DangerPiece.HitSeconds + ".");
                text.AppendLine("Danger: nothing behind the scenes; live, one strike for a stranger, " + warning.ToString("0.00") + " s of warning and " +
                                blow.ToString("0.00") + " s of blow");
            }

            table.Wearer.Animator.SetBool(striking, true);
            var kept = Watch(table.Stranger, 10f);
            table.Wearer.Animator.SetBool(striking, false);
            var cycle = DangerPiece.TelegraphSeconds + DangerPiece.HitSeconds + DangerPiece.RecoverSeconds;
            var expected = Mathf.FloorToInt(10f / cycle);
            if (Mathf.Abs(kept.strikes - expected) > 1) problems.Add("Kept striking for 10 s, the danger zone struck " + kept.strikes + " times; about " + expected + " was expected.");
            table.Run(cycle + 0.5f);
            var after = Watch(table.Stranger, 4f);
            if (after.strikes > 0) problems.Add("The danger zone went on striking after it was told to stop.");
        }

        /// <summary>
        /// The pendulum: that the wearer's clock keeps its time, that a
        /// stranger's blade crosses the middle when the wearer's does and
        /// does not fall further behind as the minutes go, and the same
        /// for someone who arrives part way through a swing and whose
        /// updates come at uneven intervals.
        /// </summary>
        private static void Pendulum(Table table, GameObject prefab, AnimatorController controller, List<string> synced, StringBuilder text, List<string> problems)
        {
            const string arm = "Stage/" + PendulumPiece.ThingName + "/Turn/Arm";
            float Angle(Client client) => Mathf.DeltaAngle(0f, At(client, arm).localEulerAngles.z);

            table.Stand(PendulumPiece.ThingName, true);
            table.GoLive(true);
            table.Run(2f);

            // When each client's blade came through the middle, and how far it has swung.
            var now = 0f;
            var crossed = new Dictionary<Client, List<float>>();
            var last = new Dictionary<Client, float>();
            var widest = new Dictionary<Client, float>();
            void Watch(Client client)
            {
                var angle = Angle(client);
                if (!crossed.ContainsKey(client))
                {
                    crossed[client] = new List<float>();
                    widest[client] = 0f;
                    last[client] = angle;
                }

                if (angle * last[client] < 0f) crossed[client].Add(now);
                if (angle != 0f) last[client] = angle;
                widest[client] = Mathf.Max(widest[client], Mathf.Abs(angle));
            }

            // Someone whose client first hears of the avatar a third of the way through a swing,
            // and hears from it afterwards at anything from a twentieth to three tenths of a second.
            Client late = null;
            var grid = new WorldGrid(512f);
            var chance = new System.Random(20261127);
            var untilHeard = 0f;
            const float joinsAt = 7.43f;
            const float watched = 60f;
            try
            {
                for (now = 0f; now < watched; now += Step)
                {
                    table.Frame();
                    if (late == null && now >= joinsAt)
                    {
                        late = new Client(prefab, controller, BusPrefix, false, false);
                        late.AlsoSynced.AddRange(synced);
                        late.Receive(table.Wearer);
                    }

                    if (late != null)
                    {
                        untilHeard -= Step;
                        if (untilHeard <= 0f)
                        {
                            late.Receive(table.Wearer);
                            untilHeard = 0.05f + 0.25f * (float)chance.NextDouble();
                        }

                        late.Ease(false);
                        late.Advance(grid);
                        Watch(late);
                    }

                    Watch(table.Wearer);
                    Watch(table.Stranger);
                }

                // The wearer's blade comes through the middle twice a swing.
                var expected = Mathf.RoundToInt(watched / PendulumPiece.SwingSeconds * 2f);
                var count = crossed[table.Wearer].Count;
                if (Mathf.Abs(count - expected) > 2)
                    problems.Add("In " + watched + " s the wearer's pendulum came through the middle " + count + " times; " + expected + " was expected.");
                foreach (var (client, name) in new[] { (table.Wearer, "the wearer"), (table.Stranger, "a stranger"), (late, "someone who arrived part way through") })
                    if (Mathf.Abs(widest[client] - PendulumPiece.SwingDegrees) > 0.5f)
                        problems.Add("For " + name + " the pendulum swings " + widest[client].ToString("0.0") + " degrees to a side; it should be " + PendulumPiece.SwingDegrees + ".");

                // How long after the wearer's blade each viewer's comes through the middle. (Here a viewer
                // can be a frame ahead: an update may arrive in the frame the wearer's clock turned the
                // bit over, which the wearer's own blade acts on a frame later.)
                (float worst, float atEnd, int counted) Behind(Client client, float from)
                {
                    var worst = 0f;
                    var atEnd = 0f;
                    var counted = 0;
                    foreach (var time in crossed[client].Where(time => time >= from))
                    {
                        if (crossed[table.Wearer].Count == 0) continue;
                        var nearest = crossed[table.Wearer].OrderBy(wearer => Mathf.Abs(wearer - time)).First();
                        atEnd = time - nearest;
                        worst = Mathf.Max(worst, Mathf.Abs(atEnd));
                        counted++;
                    }

                    return (worst, atEnd, counted);
                }

                var stranger = Behind(table.Stranger, 0f);
                // A tenth of a second of network, and a frame or two.
                if (stranger.counted < count - 2 || stranger.worst > NetworkSeconds + 0.1f)
                    problems.Add("A stranger's pendulum came through the middle " + stranger.counted + " times, up to " + stranger.worst.ToString("0.00") +
                                 " s after the wearer's; it should keep within " + (NetworkSeconds + 0.1f).ToString("0.00") + " s every time.");

                // The late client is given two swings to fall in, though it should need less than one.
                var joiner = Behind(late, joinsAt + PendulumPiece.SwingSeconds);
                var wanted = Mathf.RoundToInt((watched - joinsAt - PendulumPiece.SwingSeconds) / PendulumPiece.SwingSeconds * 2f);
                if (joiner.counted < wanted - 2 || joiner.worst > 0.3f + 0.12f)
                    problems.Add("Someone who arrived part way through, hearing from the wearer unevenly, saw the pendulum come through the middle " + joiner.counted +
                                 " times (about " + wanted + " expected), up to " + joiner.worst.ToString("0.00") + " s after the wearer's; no update was more than 0.30 s late.");
                var soon = Behind(late, joinsAt).counted - joiner.counted;
                text.AppendLine("Pendulum: " + count + " passes through the middle in " + watched + " s for the wearer; a stranger's blade at most " +
                                stranger.worst.ToString("0.00") + " s behind; someone arriving part way through, with updates up to 0.30 s apart, at most " +
                                joiner.worst.ToString("0.00") + " s behind and " + joiner.atEnd.ToString("0.00") + " s at the end, in step from their first full swing (" +
                                soon + " passes in it)");
            }
            finally
            {
                late?.Dispose();
            }

            // Taken away, the clock stops; set out again, it starts.
            table.Wearer.Animator.SetBool(On(PendulumPiece.ThingName), false);
            table.Run(PendulumPiece.SwingSeconds * 1.5f);
            if (!In(table.Wearer, controller, "Pendulum Clock", "Stopped")) problems.Add("The pendulum's clock goes on running after the pendulum is taken away.");
            var swing = PendulumPiece.Swing(CryptPrefix);
            var flips = 0;
            var held = table.Wearer.Animator.GetBool(swing);
            table.Run(PendulumPiece.SwingSeconds * 2f, () =>
            {
                if (table.Wearer.Animator.GetBool(swing) != held) flips++;
                held = table.Wearer.Animator.GetBool(swing);
            });
            if (flips > 0) problems.Add("With the pendulum taken away its synced bit still turned over " + flips + " times.");
        }

        /// <summary>The rift: sealing, creeping open when left, and staying shut once shut.</summary>
        private static void Rift(Table table, AnimatorController controller, StringBuilder text, List<string> problems)
        {
            var check = Named("crypt-sealed");
            const string tear = "Stage/" + RiftPiece.ThingName + "/Float/Tear";
            void Touch(bool touching)
            {
                foreach (var client in new[] { table.Wearer, table.Backstage }) client.Animator.SetFloat(check.Touching(SkillTags.Hand), touching ? 1f : 0f);
            }

            table.Stand(RiftPiece.ThingName, true);
            table.GoLive(true);
            table.Run(1f);
            if (!In(table.Stranger, controller, "Rift Hum", "Humming")) problems.Add("An open rift does not hum for a stranger.");

            Touch(true);
            table.Run(RiftPiece.SealSeconds * 0.5f);
            Touch(false);
            var half = table.Wearer.Animator.GetFloat(check.Progress);
            table.Run(4f);
            var crept = table.Wearer.Animator.GetFloat(check.Progress);
            var expected = SkillClock.Extrapolate(half, -1f / RiftPiece.ReopenSeconds, 0.0, 4.0);
            if (Mathf.Abs(half - 0.5f) > 0.04f) problems.Add("After half the sealing time the rift is " + half.ToString("0.00") + " sealed.");
            if (Mathf.Abs(crept - expected) > 0.03f)
                problems.Add("Left for 4 s, a half-sealed rift went to " + crept.ToString("0.00") + "; the check's rules say " + expected.ToString("0.00") + ".");

            Touch(true);
            var seconds = 0f;
            while (seconds < RiftPiece.SealSeconds && !table.Wearer.Animator.GetBool(check.Done))
            {
                table.Frame();
                seconds += Step;
            }

            table.Run(0.6f);
            Touch(false);
            table.Run(3f);
            if (!table.Wearer.Animator.GetBool(check.Done)) problems.Add("Hands on the rift did not seal it.");
            foreach (var (client, name) in new[] { (table.Wearer, "the wearer"), (table.Stranger, "a stranger who saw no contact") })
            {
                if (Size(client, tear) > 0.02f) problems.Add("The rift is sealed and " + name + " still sees it open.");
                if (!In(client, controller, "Rift Hum", "Sealed")) problems.Add("The rift is sealed and still hums for " + name + ".");
            }

            text.AppendLine("Rift: half sealed after " + (RiftPiece.SealSeconds * 0.5f) + " s of hands, back to " + crept.ToString("0.00") +
                            " after 4 s alone, then shut and silent for everyone, and it stays shut");
        }

        /// <summary>A size and a heading, set by the wearer, reach a viewer by the bus.</summary>
        private static void Values(Table table, StringBuilder text, List<string> problems)
        {
            var hot = ElementPiece.ThingName(ElementPiece.Elements[0]);
            string Value(string thing) => BusPrefix + "/" + table.Slots[thing] + "/Value";
            float Radius(Client client) => Size(client, "Stage/" + hot + "/Size");
            float Heading(Client client) => At(client, "Stage/" + BarricadePiece.ThingName + "/Turn").localEulerAngles.y;

            table.Stand(hot, true);
            table.Stand(BarricadePiece.ThingName, true);
            table.GoLive(true);
            table.Run(2f);

            table.Wearer.Animator.SetFloat(Value(hot), 1f);
            table.Wearer.Animator.SetFloat(Value(BarricadePiece.ThingName), 0.25f);
            var heardSize = -1f;
            var heardTurn = -1f;
            var elapsed = 0f;
            table.Run(6f, () =>
            {
                elapsed += Step;
                if (heardSize < 0f && Mathf.Abs(Radius(table.Stranger) - ElementPiece.LargestRadius) < 0.05f) heardSize = elapsed;
                if (heardTurn < 0f && Mathf.Abs(Mathf.DeltaAngle(Heading(table.Stranger), 90f)) < 2f) heardTurn = elapsed;
            });
            if (Mathf.Abs(Radius(table.Wearer) - ElementPiece.LargestRadius) > 0.01f) problems.Add("The wearer's own hot zone did not take the size they dialled.");
            if (heardSize < 0f || heardSize > 4f) problems.Add("A size the wearer dialled had not reached a stranger after " + (heardSize < 0f ? "6" : heardSize.ToString("0.0")) + " s.");
            if (heardTurn < 0f || heardTurn > 4f) problems.Add("A heading the wearer dialled had not reached a stranger after " + (heardTurn < 0f ? "6" : heardTurn.ToString("0.0")) + " s.");
            text.AppendLine("Values: a size dialled by the wearer is with a stranger after " + heardSize.ToString("0.0") + " s, and a heading dialled at the same moment after " +
                            heardTurn.ToString("0.0") + " s");
        }
    }
}
