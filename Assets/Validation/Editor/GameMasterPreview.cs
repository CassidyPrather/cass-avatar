using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Wirenook.AdventureTools.Core;
using Wirenook.AdventureTools.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Pictures of the game master's kit (net.wirenook.adventure-tools):
    /// the dice boards, a zone on uneven ground, the pause from outside and
    /// from inside, the portal, the light and the laser, the skeleton key.
    /// The kit's prefab is played on an animator of its own, with the
    /// parameters set to what a client would hold, so this shows the shapes
    /// and what the layers do with them, shaders included. Nothing here
    /// casts a ray, runs a constraint or carries out a parameter driver:
    /// everything stands where it rests, at the kit's own origin.
    /// </summary>
    public static class GameMasterPreview
    {
        private const string Prefix = "GM";
        private const string Stage = Prefix + "/Stage";

        private static string On(string thing) => Stage + "/" + thing.Replace(" ", "");
        private static string Placed(int slot) => Stage + "/Bus/" + slot + "/Set";
        private static string Value(int slot) => Stage + "/Bus/" + slot + "/Value";

        /// <returns>The folder the pictures were written to.</returns>
        public static string Render()
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "dm");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var scene = ValidationScene.Open(out _);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(GameMasterBuild.KitPrefab);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
            var rig = new GameObject("Game Master Preview Camera");
            var props = new GameObject("Game Master Preview Props");
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(rig, scene);
            UnityEngine.SceneManagement.SceneManager.MoveGameObjectToScene(props, scene);
            try
            {
                var animator = instance.AddComponent<Animator>();
                animator.runtimeAnimatorController = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(GameMasterBuild.KitController);
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

                void Shot(string label, Vector3 from, Vector3 at, float fieldOfView = 40f)
                {
                    camera.fieldOfView = fieldOfView;
                    camera.transform.SetPositionAndRotation(from, Quaternion.LookRotation(at - from, Vector3.up));
                    ContactSheets.Capture(camera, Path.Combine(folder, "dm", index++.ToString("000") + " " + label + ".png"));
                }

                void Roll(Roll roll, int first, int second)
                {
                    animator.SetFloat(DiceTool.First(Prefix), first);
                    animator.SetFloat(DiceTool.Second(Prefix), second);
                    for (var bit = 0; bit < DiceModel.KindBits; bit++) animator.SetBool(DiceTool.Kind(Prefix, bit), DiceModel.Bit(roll, bit));
                    Play(0.6f);
                }

                var board = new Vector3(0f, 2.19f, 0f);

                // Someone else's client.
                animator.SetBool("IsLocal", false);
                Roll(Wirenook.AdventureTools.Core.Roll.TwoD20, 17, 5);
                Shot("dice, 2d20 of 17 and 5, from in front", board + new Vector3(0f, -0.1f, 1.6f), board);
                Shot("dice, the same from behind", board + new Vector3(0f, -0.1f, -1.6f), board);
                Roll(Wirenook.AdventureTools.Core.Roll.D20, 20, 0);
                Shot("dice, 1d20 of 20", board + new Vector3(0.5f, -0.1f, 1.5f), board);
                Roll(Wirenook.AdventureTools.Core.Roll.TwoD6, 6, 3);
                Shot("dice, 2d6 of 6 and 3", board + new Vector3(0f, -0.1f, 1.6f), board);
                Roll(Wirenook.AdventureTools.Core.Roll.D6, 4, 0);
                Shot("dice, 1d6 of 4", board + new Vector3(0f, -0.1f, 1.6f), board);
                Roll(Wirenook.AdventureTools.Core.Roll.Coin, 1, 0);
                Shot("dice, a coin, heads", board + new Vector3(0f, -0.1f, 1.6f), board);
                Roll(Wirenook.AdventureTools.Core.Roll.Coin, 2, 0);
                Shot("dice, a coin, tails", board + new Vector3(0f, -0.1f, 1.6f), board);

                // In secret: nothing over the head for a stranger, and the wearer's own board.
                animator.SetBool(DiceTool.Secret(Prefix), true);
                Roll(Wirenook.AdventureTools.Core.Roll.TwoD6, 2, 5);
                Shot("dice, in secret, to a stranger", board + new Vector3(0f, -0.1f, 1.6f), board);
                animator.SetBool("IsLocal", true);
                Play(0.6f);
                var eyes = new Vector3(0f, 1.55f, 0f);
                Shot("dice, in secret, the wearer's own board from their eyes", eyes, new Vector3(0f, 1.25f, 0.4f), 60f);
                animator.SetBool("IsLocal", false);
                animator.SetBool(DiceTool.Secret(Prefix), false);
                Roll(Wirenook.AdventureTools.Core.Roll.None, 0, 0);

                // Uneven ground for the zone to cross.
                void Block(Vector3 centre, Vector3 size)
                {
                    var block = GameObject.CreatePrimitive(PrimitiveType.Cube);
                    block.transform.SetParent(props.transform, false);
                    block.transform.position = centre;
                    block.transform.localScale = size;
                }

                Block(new Vector3(2.4f, 0.4f, 0.6f), new Vector3(1.6f, 0.8f, 1.6f));
                Block(new Vector3(-1.2f, 0.2f, -2.2f), new Vector3(2.2f, 0.4f, 1.4f));
                Block(new Vector3(-3.4f, 1f, 0.5f), new Vector3(0.4f, 2f, 5f));
                Block(new Vector3(0.6f, 0.6f, 2.6f), new Vector3(0.8f, 1.2f, 0.8f));

                // Slots: the pause is 1, the zones 2 to 4, the door 5 and the way out 6.
                animator.SetBool(On("Zone 1"), true);
                animator.SetBool(Placed(2), true);
                animator.SetFloat(Value(2), ZoneModel.Amount(3f));
                Play(0.6f);
                Shot("zone, 3 m, on uneven ground", new Vector3(5.5f, 4.5f, 6.5f), new Vector3(0f, 0.3f, 0f), 50f);
                Shot("zone, 3 m, from a person's height", new Vector3(1.5f, 1.6f, 7f), new Vector3(0f, 0.8f, 0f), 55f);
                Shot("zone, 3 m, from inside it", new Vector3(-0.6f, 1.6f, -0.8f), new Vector3(2.4f, 0.2f, 1.2f), 75f);
                animator.SetFloat(Value(2), ZoneModel.Amount(1.5f));
                Play(0.3f);
                Shot("zone, 1.5 m", new Vector3(3f, 2.6f, 4f), new Vector3(0f, 0.3f, 0f), 50f);
                animator.SetBool(On("Zone 1"), false);
                Play(0.4f);

                animator.SetBool(On("Pause"), true);
                animator.SetBool(Placed(1), true);
                animator.SetFloat(Value(1), ZoneModel.Amount(3f));
                Play(0.8f);
                Shot("pause, 3 m, from outside", new Vector3(5.5f, 3.6f, 6.5f), new Vector3(0f, 1.2f, 0f), 50f);
                Shot("pause, from inside (the card is on screen)", new Vector3(1.2f, 1.6f, -1.4f), new Vector3(-2f, 1f, 2.5f), 70f);
                animator.SetBool(On("Pause"), false);
                Play(0.4f);

                animator.SetBool(On("Door"), true);
                animator.SetBool(Placed(5), true);
                Play(0.8f);
                Shot("portal, the door", new Vector3(2.2f, 1.7f, 3.4f), new Vector3(0f, 1.05f, 0f), 45f);
                animator.SetBool(On("Door"), false);
                animator.SetBool(On("Exit"), true);
                animator.SetBool(Placed(6), true);
                Play(0.6f);
                Shot("portal, the way out", new Vector3(1.2f, 1.2f, 1.6f), new Vector3(0f, 0f, 0f), 45f);
                animator.SetBool(On("Exit"), false);
                Play(0.4f);

                // The pointer. With no hand to ride, it rests at the kit's origin and points along +Z.
                props.SetActive(false);
                animator.SetBool(Prefix + "/Finger", true);
                Play(0.6f);
                Shot("finger light", new Vector3(0.25f, 0.12f, 0.3f), Vector3.zero, 30f);
                animator.SetBool(Prefix + "/Finger/Laser", true);
                animator.SetBool(Prefix + "/Finger/Ray_Hit", true);
                animator.SetFloat(Prefix + "/Finger/Ray_Ratio", 2f / 30f);
                var dot = instance.transform.Find("Dot");
                dot.position = new Vector3(0f, 0f, 2f);
                Play(0.6f);
                Shot("laser, two metres to its dot", new Vector3(1.6f, 0.5f, -0.6f), new Vector3(0f, 0f, 1f), 45f);
                animator.SetBool(Prefix + "/Finger/Laser", false);
                animator.SetBool(Prefix + "/Finger", false);

                // The wearer aiming: the mark.
                animator.SetBool("IsLocal", true);
                animator.SetInteger(Stage + "/Aim", 2);
                Play(0.6f);
                Shot("aiming a zone, the wearer's view of it and of the mark", new Vector3(2.6f, 2.2f, 3.4f), new Vector3(0f, 0.3f, 0f), 50f);
                animator.SetInteger(Stage + "/Aim", 0);
                animator.SetBool("IsLocal", false);
                Play(0.4f);

                // The key, sending fire, feeling fire, water and a blade.
                animator.SetBool(KeyTool.Out(Prefix), true);
                animator.SetInteger(KeyTool.Trait(Prefix), KeyModel.Number("Fire"));
                foreach (var tag in new[] { "Fire", "Water", "DamageSharp" }) animator.SetFloat(KeyTool.Feels(Prefix, tag), 1f);
                Play(0.6f);
                var key = new Vector3(0.14f, 0f, 0f);
                Shot("skeleton key, sending Fire, feeling Fire, Water and DamageSharp", key + new Vector3(0.12f, 0.5f, -0.38f), key, 35f);
                Shot("skeleton key, its dial", new Vector3(0.26f, 0.3f, -0.08f), new Vector3(0.26f, 0f, 0f), 30f);
                animator.SetInteger(KeyTool.Trait(Prefix), 0);
                foreach (var tag in new[] { "Fire", "Water", "DamageSharp" }) animator.SetFloat(KeyTool.Feels(Prefix, tag), 0f);
                Play(0.4f);
                Shot("skeleton key, feeling nothing and sending nothing", key + new Vector3(0.12f, 0.5f, -0.38f), key, 35f);
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
