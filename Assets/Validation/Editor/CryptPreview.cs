using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Wirenook.AdventureTools.Core;
using Wirenook.AdventureTools.Editor;
using Wirenook.Meta.Crypt.Editor;
using Wirenook.SelectiveAnimation.Core;
using Wirenook.SkillChecks;
using Wirenook.SkillChecks.Avatar.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Pictures of the pieces a game master's kit gains for The Sunken
    /// Crypt (net.wirenook.meta-avatar): the zones of an element, the
    /// danger zone warning and striking, the barricade whole, half down
    /// and burning, the chest and its key, the pendulum, the rift from two
    /// sides and half sealed, and the course as the people backstage see
    /// it before it is live.
    ///
    /// As <see cref="GameMasterPreview"/>: the kit's prefab is played on
    /// an animator of its own with the parameters set to what a client
    /// would hold. Nothing casts a ray, runs a constraint or carries out
    /// a driver, and no contact is real: what a contact would report is
    /// written into the animator. Everything stands at the kit's origin,
    /// so one thing is shown at a time.
    /// </summary>
    public static class CryptPreview
    {
        private const string Prefix = "GM";
        private const string StagePrefix = Prefix + "/Stage";

        /// <returns>The folder the pictures were written to.</returns>
        public static string Render()
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "crypt");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var plan = new StagePlan();
            foreach (var tool in CryptBuild.Tools()) tool.Things(plan);
            var slots = plan.Things.Select((thing, index) => (thing.name, slot: index + 1)).ToDictionary(pair => pair.name, pair => pair.slot);
            string On(string thing) => StagePrefix + "/" + thing.Replace(" ", "");
            string Placed(string thing) => StagePrefix + "/Bus/" + slots[thing] + "/Set";
            string Value(string thing) => StagePrefix + "/Bus/" + slots[thing] + "/Value";
            AvatarCheck Check(string name) => new AvatarCheck(name, new CheckSpec());

            var scene = ValidationScene.Open(out _);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(CryptBuild.KitPrefab);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
            var rig = new GameObject("Crypt Preview Camera");
            var props = new GameObject("Crypt Preview Props");
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(rig, scene);
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(props, scene);
            try
            {
                var animator = instance.AddComponent<Animator>();
                animator.runtimeAnimatorController = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(CryptBuild.KitController);
                animator.Rebind();
                animator.Update(0f);
                foreach (var skinned in instance.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                    skinned.forceMatrixRecalculationPerRender = true;

                var camera = rig.AddComponent<Camera>();
                camera.CopyFrom(ValidationScene.Cameras(scene).First(candidate => candidate.name == "Front"));
                camera.nearClipPlane = 0.05f;
                camera.farClipPlane = 200f;
                var index = 0;

                void Play(float seconds)
                {
                    for (var time = 0f; time < seconds; time += 1f / 72f) animator.Update(1f / 72f);
                }

                void Shot(string label, Vector3 from, Vector3 at, float fieldOfView = 45f)
                {
                    camera.fieldOfView = fieldOfView;
                    camera.transform.SetPositionAndRotation(from, Quaternion.LookRotation(at - from, Vector3.up));
                    ContactSheets.Capture(camera, Path.Combine(folder, "crypt", index++.ToString("000") + " " + label + ".png"));
                }

                void Block(Vector3 centre, Vector3 size)
                {
                    var block = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    block.transform.SetParent(props.transform, false);
                    block.transform.position = centre;
                    block.transform.localScale = size;
                }

                void Out(string thing, bool shown)
                {
                    animator.SetBool(On(thing), shown);
                    animator.SetBool(Placed(thing), shown);
                }

                Block(new Vector3(2.2f, 0.3f, -1.4f), new Vector3(1.4f, 0.6f, 1.4f));
                Block(new Vector3(-3.6f, 1f, -1.5f), new Vector3(0.4f, 2f, 6f));
                Block(new Vector3(0f, 1.2f, -4.4f), new Vector3(7f, 2.4f, 0.4f));

                // The wearer's own client, with the course live: theirs is the
                // one that says when a check is complete.
                animator.SetBool("IsLocal", true);
                animator.SetBool(StagePrefix + "/Live", true);

                foreach (var element in ElementPiece.Elements)
                {
                    var name = ElementPiece.ThingName(element);
                    Out(name, true);
                    animator.SetFloat(Value(name), 0.55f);
                    Play(2.2f);
                    Shot(name.ToLowerInvariant() + ", 2 m", new Vector3(3.6f, 2.6f, 4.4f), new Vector3(0f, 0.5f, 0f), 50f);
                    if (element.Name == "Hot") Shot("hot zone, from a person's height", new Vector3(0.8f, 1.6f, 4.6f), new Vector3(0f, 0.6f, 0f), 55f);
                    Out(name, false);
                    Play(0.4f);
                }

                Out(DangerPiece.ThingName, true);
                animator.SetFloat(Value(DangerPiece.ThingName), 0.55f);
                Play(0.6f);
                Shot("danger zone, at rest", new Vector3(3.2f, 2.8f, 4f), new Vector3(0f, 0.2f, 0f), 50f);
                animator.SetBool(DangerPiece.Striking(Prefix + "/Crypt"), true);
                Play(1.2f);
                Shot("danger zone, the warning half way", new Vector3(3.2f, 2.8f, 4f), new Vector3(0f, 0.2f, 0f), 50f);
                Play(DangerPiece.TelegraphSeconds - 1.2f + 0.2f);
                Shot("danger zone, striking", new Vector3(3.2f, 2.8f, 4f), new Vector3(0f, 0.2f, 0f), 50f);
                animator.SetBool(DangerPiece.Striking(Prefix + "/Crypt"), false);
                Out(DangerPiece.ThingName, false);
                Play(1.5f);

                // The barricade, under a hand, and then under fire.
                var barricade = Check("crypt-barricade");
                Out(BarricadePiece.ThingName, true);
                Play(0.6f);
                Shot("barricade, whole", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
                animator.SetFloat(barricade.Touching(SkillTags.Hand), 1f);
                Play(BarricadePiece.TakesSeconds * 0.5f);
                Shot("barricade, after five seconds of hands", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
                animator.SetFloat(barricade.Touching(SkillTags.Hand), 0f);
                animator.SetFloat(barricade.Touching(SkillTags.Fire), 1f);
                Play(BarricadePiece.TakesSeconds * 0.25f);
                Shot("barricade, burning", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
                Play(BarricadePiece.TakesSeconds * 0.3f);
                animator.SetFloat(barricade.Touching(SkillTags.Fire), 0f);
                Play(0.3f);
                Shot("barricade, down", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
                animator.SetFloat(Value(BarricadePiece.ThingName), 0.125f);
                Out(BarricadePiece.ThingName, false);
                Play(0.4f);
                Out(BarricadePiece.ThingName, true);
                Play(0.8f);
                Shot("barricade, set out again, turned an eighth", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
                Out(BarricadePiece.ThingName, false);
                Play(0.4f);

                // The chest and its key.
                var found = Check("crypt-found");
                var opened = Check("crypt-opened");
                Out(ChestPiece.KeyName, true);
                Play(0.8f);
                Shot("the key, where it was left", new Vector3(0.5f, 0.8f, 1f), new Vector3(0f, 0.45f, 0f), 35f);
                Out(ChestPiece.ChestName, true);
                // The two stand in one place here; move the key aside for the picture.
                instance.transform.Find("Stage/" + ChestPiece.KeyName).localPosition = new Vector3(0.8f, 0f, 0.4f);
                Play(0.6f);
                Shot("chest, locked, and its key", new Vector3(1.2f, 1.1f, 1.9f), new Vector3(0.2f, 0.3f, 0f), 40f);
                animator.SetFloat(opened.Touching(SkillTags.Hand), 1f);
                Play(0.2f);
                Shot("chest, rattled by a hand with no key", new Vector3(0.5f, 0.7f, 1.1f), new Vector3(0f, 0.3f, 0.2f), 35f);
                Play(1.5f);
                animator.SetFloat(opened.Touching(SkillTags.Hand), 0f);
                animator.SetFloat(found.Touching(SkillTags.Hand), 1f);
                Play(0.8f);
                animator.SetFloat(found.Touching(SkillTags.Hand), 0f);
                animator.SetFloat(opened.Touching(SkillTags.Hand), 1f);
                Play(1.2f);
                animator.SetFloat(opened.Touching(SkillTags.Hand), 0f);
                Shot("chest, opened once the key was taken", new Vector3(1.2f, 1.1f, 1.9f), new Vector3(0.2f, 0.3f, 0f), 40f);
                Out(ChestPiece.ChestName, false);
                Out(ChestPiece.KeyName, false);
                Play(0.4f);

                Out(PendulumPiece.ThingName, true);
                Play(0.4f + PendulumPiece.SwingSeconds * 0.5f);
                Shot("pendulum, at one end of its swing", new Vector3(1.4f, 1.7f, 6.2f), new Vector3(0f, 1.6f, 0f), 50f);
                Play(PendulumPiece.SwingSeconds * 0.25f);
                Shot("pendulum, coming through the middle", new Vector3(3.6f, 1.7f, 5f), new Vector3(0f, 1.5f, 0f), 50f);
                Out(PendulumPiece.ThingName, false);
                Play(0.4f);

                // The rift.
                var sealing = Check("crypt-sealed");
                var middle = new Vector3(0f, RiftPiece.Height, 0f);
                Out(RiftPiece.ThingName, true);
                Play(0.8f);
                Shot("rift, from in front", middle + new Vector3(0f, 0.1f, 2.4f), middle, 40f);
                Shot("rift, from a step to the side", middle + new Vector3(1.1f, 0.1f, 2.1f), middle, 40f);
                Shot("rift, towards the eye", middle - new Vector3(0.55f, 0.3f, 0.78f).normalized * 2.2f, middle, 40f);
                Shot("rift, in the room", new Vector3(2.6f, 1.7f, 4.2f), new Vector3(0f, 1.2f, 0f), 50f);
                animator.SetFloat(sealing.Touching(SkillTags.Hand), 1f);
                Play(RiftPiece.SealSeconds * 0.72f);
                Shot("rift, most of the way sealed", middle + new Vector3(0f, 0.1f, 2.4f), middle, 40f);
                Play(RiftPiece.SealSeconds * 0.35f);
                animator.SetFloat(sealing.Touching(SkillTags.Hand), 0f);
                Shot("rift, sealed", middle + new Vector3(0f, 0.1f, 2.4f), middle, 40f);
                Out(RiftPiece.ThingName, false);
                Play(0.4f);

                // Behind the scenes: the course before it is live, to someone backstage, and to a stranger.
                animator.SetBool("IsLocal", false);
                animator.SetBool(StagePrefix + "/Live", false);
                animator.SetBool(CircleNames.Seen(PresenceModel.BackstageCircle), true);
                Out(BarricadePiece.ThingName, true);
                Play(1f);
                Shot("rehearsal, the barricade to someone backstage", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
                animator.SetBool(CircleNames.Seen(PresenceModel.BackstageCircle), false);
                Play(0.6f);
                Shot("rehearsal, the same to a stranger", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
                animator.SetBool(StagePrefix + "/Live", true);
                Play(0.8f);
                Shot("live, the same to a stranger", new Vector3(1.6f, 1.5f, 3.6f), new Vector3(0f, 0.8f, 0f));
            }
            finally
            {
                Object.DestroyImmediate(rig);
                Object.DestroyImmediate(props);
                Object.DestroyImmediate(instance);
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
