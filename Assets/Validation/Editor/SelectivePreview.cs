using System.IO;
using System.Linq;
using UnityEditor;
using UnityEngine;
using Wirenook.SelectiveAnimation.Core;
using Wirenook.SelectiveAnimation.Editor;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Pictures of the selective-animation probe: its lamps and its reticle,
    /// in the states one viewer's client or the wearer's own would have
    /// them in. The prefab is played on an animator of its own, with the
    /// parameters set to what a client would hold, so this shows the shapes
    /// and what the layers do with them. Nothing here casts a ray.
    /// </summary>
    public static class SelectivePreview
    {
        /// <returns>The folder the pictures were written to.</returns>
        public static string Render()
        {
            var folder = Path.Combine(ContactSheets.OutputFolder, "selective");
            if (Directory.Exists(folder)) Directory.Delete(folder, true);

            var names = new SelectorNames();
            var scene = ValidationScene.Open(out _);
            var prefab = AssetDatabase.LoadAssetAtPath<GameObject>(SelectiveAnimationBuild.ProbePrefab);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab, scene);
            var rig = new GameObject("Selective Preview Camera");
            try
            {
                var animator = instance.AddComponent<Animator>();
                animator.runtimeAnimatorController = AssetDatabase.LoadAssetAtPath<RuntimeAnimatorController>(SelectiveAnimationBuild.ProbeController);
                animator.Rebind();
                animator.Update(0f);
                foreach (var skinned in instance.GetComponentsInChildren<SkinnedMeshRenderer>(true))
                    skinned.forceMatrixRecalculationPerRender = true;

                var camera = rig.AddComponent<Camera>();
                camera.CopyFrom(ValidationScene.Cameras(scene).First(candidate => candidate.name == "Front"));
                var index = 0;

                void Play(float seconds)
                {
                    for (var time = 0f; time < seconds; time += 1f / 72f) animator.Update(1f / 72f);
                }

                void Shot(string label, Transform target, float distance, bool behind = false)
                {
                    // The lamps are looked at from in front of the wearer; the reticle from where the wearer stands.
                    var rotation = Quaternion.Euler(8f, behind ? 0f : 180f, 0f);
                    camera.transform.SetPositionAndRotation(target.position - rotation * Vector3.forward * distance, rotation);
                    ContactSheets.Capture(camera, Path.Combine(folder, "selective", index++.ToString("000") + " " + label + ".png"));
                }

                var row = instance.GetComponentsInChildren<Transform>(true).First(candidate => candidate.name == "Row");
                var reticle = instance.GetComponentsInChildren<Transform>(true).First(candidate => candidate.name == "Reticle");

                // A viewer's client.
                animator.SetBool("IsLocal", false);
                animator.SetBool(SelectiveAnimationBuild.ProbeShown, true);
                Play(0.3f);
                Shot("lamps, a viewer nothing is true for", row, 1.1f);

                animator.SetBool(names.Aim, true);
                animator.SetBool(names.MeHit, true);
                animator.SetFloat(names.MeRatio, 0.2f);
                animator.SetFloat(names.SightRatio, 1f);
                Play(0.2f);
                Shot("lamps, the viewer pointed at", row, 1.1f);

                animator.SetBool(names.Mark, true);
                Play(0.6f);
                animator.SetBool(names.Mark, false);
                animator.SetBool(names.MeHit, false);
                animator.SetBool(CircleNames.Seen(SelectiveAnimationBuild.ProbeCircle), true);
                animator.SetBool(SelectiveAnimationBuild.ProbeDriven, true);
                Play(0.6f);
                Shot("lamps, selected, in the circle, driver ran", row, 1.1f);

                // The wearer's own.
                animator.SetBool("IsLocal", true);
                animator.SetBool(SelectiveAnimationBuild.ProbeShown, false);
                animator.SetFloat(names.SightRatio, 2f / SelectiveAnimationBuild.Full().Reach);
                Play(0.3f);
                Shot("reticle, on nothing, 2 m away", reticle, 0.4f, behind: true);

                animator.SetBool(names.SightHit, true);
                animator.SetBool(names.OnPerson, true);
                Play(0.3f);
                Shot("reticle, on someone", reticle, 0.4f, behind: true);

                animator.SetBool(names.Mark, true);
                Play(0.3f);
                Shot("reticle, holding mark", reticle, 0.4f, behind: true);
                Play(1f);
                Shot("reticle, marked", reticle, 0.4f, behind: true);

                animator.SetBool(names.Mark, false);
                animator.SetBool(names.Unmark, true);
                Play(1.5f);
                Shot("reticle, unmarked", reticle, 0.4f, behind: true);
            }
            finally
            {
                Object.DestroyImmediate(rig);
                Object.DestroyImmediate(instance);
            }

            ContactSheets.Compose(folder);
            return Path.GetFullPath(folder);
        }
    }
}
