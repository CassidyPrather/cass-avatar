using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Threading.Tasks;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using VRC.Core;
using VRC.SDK3A.Editor;
using VRC.SDKBase.Editor;
using VRC.SDKBase.Editor.Api;
using Wirenook.Cass.Core;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Uploads a variant with its name, description, tags, visibility and
    /// thumbnail filled in from the project instead of typed into the SDK
    /// panel, and refuses when the result would break the upload policy.
    ///
    /// VRChat still asks the person uploading to confirm they hold the rights
    /// to the content. That confirmation is theirs to give, so this drives the
    /// SDK's own upload path and leaves that dialog to them.
    /// </summary>
    public static class CassUpload
    {
        /// <summary>True while an upload started here is running, so the panel hook stands down.</summary>
        public static bool Running { get; private set; }

        [MenuItem("Tools/Wirenook/Cass/Upload cass")]
        private static void UploadDefaultMenu() => UploadFromMenu("cass");

        [MenuItem("Tools/Wirenook/Cass/Upload cass-adv")]
        private static void UploadAdventureMenu() => UploadFromMenu("cass-adv");

        private static async void UploadFromMenu(string slug)
        {
            try
            {
                var result = await Upload(slug);
                EditorUtility.DisplayDialog("Uploaded " + slug, result, "OK");
            }
            catch (Exception e)
            {
                Debug.LogException(e);
                EditorUtility.DisplayDialog("Upload of " + slug + " failed", e.Message, "OK");
            }
        }

        /// <summary>What an upload of a variant would send, without sending it.</summary>
        public static string Preview(string slug)
        {
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(CassBuild.LoadVariant(slug));
            try
            {
                var record = Compose(instance, default, out var dropped);
                var problems = Check(record);
                return "name: " + record.Name + "\n" +
                       "description: " + record.Description + "\n" +
                       "tags: " + string.Join(", ", record.Tags) + "\n" +
                       (dropped.Count > 0 ? "dropped tags (over the limit): " + string.Join(", ", dropped) + "\n" : "") +
                       "release: " + record.ReleaseStatus + "\n" +
                       "blueprint: " + Blueprint(instance) + "\n" +
                       (problems.Count == 0 ? "policy: ok" : "policy: FAILS\n  " + string.Join("\n  ", problems));
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(instance);
            }
        }

        /// <summary>What VRChat currently holds for a variant that has been uploaded.</summary>
        public static async Task<string> Live(string slug)
        {
            var pipeline = CassBuild.LoadVariant(slug).GetComponent<PipelineManager>();
            var blueprint = pipeline != null ? pipeline.blueprintId : "";
            if (string.IsNullOrEmpty(blueprint)) return slug + " has not been uploaded.";

            await SignedIn();
            var live = await VRCApi.GetAvatar(blueprint, true);
            var problems = Check(live);
            return "id: " + live.ID + "\n" +
                   "name: " + live.Name + "\n" +
                   "description: " + live.Description + "\n" +
                   "tags: " + string.Join(", ", live.Tags ?? new List<string>()) + "\n" +
                   "release: " + live.ReleaseStatus + "\n" +
                   (problems.Count == 0 ? "policy: ok" : "policy: FAILS\n  " + string.Join("\n  ", problems));
        }

        /// <summary>
        /// Sends a variant's name, description, tags and visibility to
        /// VRChat without building or uploading the avatar again.
        /// </summary>
        public static async Task<string> Publish(string slug)
        {
            await SignedIn();

            var instance = (GameObject)PrefabUtility.InstantiatePrefab(CassBuild.LoadVariant(slug));
            try
            {
                var blueprint = Blueprint(instance);
                if (string.IsNullOrEmpty(blueprint)) return slug + " has not been uploaded.";
                await SendRecord(instance, blueprint);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(instance);
            }

            return await Live(slug);
        }

        /// <summary>
        /// Waits for the SDK to be signed in. It signs itself in again after
        /// every script reload, but only once its control panel has been
        /// drawn, so a panel that is closed or hidden behind another tab
        /// leaves it signed out indefinitely.
        /// </summary>
        private static async Task<IVRCSdkAvatarBuilderApi> SignedIn()
        {
            IVRCSdkAvatarBuilderApi builder = null;
            bool Ready() => APIUser.IsLoggedIn && VRCSdkControlPanel.TryGetBuilder(out builder);

            if (Ready()) return builder;
            EditorApplication.ExecuteMenuItem("VRChat SDK/Show Control Panel");
            for (var waited = 0; waited < 40 && !Ready(); waited++) await Task.Delay(500);
            if (Ready()) return builder;

            throw new InvalidOperationException(APIUser.IsLoggedIn
                ? "The VRChat SDK control panel has not shown its Builder tab. Open it and run this again."
                : "Sign in to VRChat in the SDK control panel (it is open now), then run this again.");
        }

        /// <summary>Replaces the name, description, tags and visibility VRChat holds with the variant's.</summary>
        /// <returns>VRChat's record afterwards.</returns>
        private static async Task<VRCAvatar> SendRecord(GameObject instance, string blueprint)
        {
            var live = await VRCApi.GetAvatar(blueprint, true);
            var record = Compose(instance, live, out _);
            var problems = Check(record);
            if (problems.Count > 0)
                throw new InvalidOperationException("Refused by the upload policy:\n  " + string.Join("\n  ", problems));

            await VRCApi.UpdateAvatarInfo(blueprint, record);
            return await VRCApi.GetAvatar(blueprint, true);
        }

        /// <summary>Builds and uploads a variant. Needs an account signed in through the SDK control panel.</summary>
        public static async Task<string> Upload(string slug)
        {
            var builder = await SignedIn();

            var thumbnail = Thumbnail(slug, out var report);

            var prefab = CassBuild.LoadVariant(slug);
            var instance = (GameObject)PrefabUtility.InstantiatePrefab(prefab);
            Running = true;
            try
            {
                var blueprint = Blueprint(instance);
                var existing = string.IsNullOrEmpty(blueprint) ? default : await VRCApi.GetAvatar(blueprint, true);
                var record = Compose(instance, existing, out var dropped);
                foreach (var tag in dropped)
                    Debug.LogWarning("[cass] Tag " + tag + " was dropped: VRChat accepts " + Wirenook.Assets.Core.FeatureTags.Limit + " tags per avatar.");

                var problems = Check(record);
                if (problems.Count > 0)
                    throw new InvalidOperationException("Upload refused by the upload policy:\n  " + string.Join("\n  ", problems));

                await builder.BuildAndUpload(instance, record, thumbnail);

                // The SDK writes a newly reserved id onto the scene copy only;
                // keep it with the variant so the next upload updates the same avatar.
                var assigned = Blueprint(instance);
                if (assigned != blueprint) SaveBlueprint(slug, assigned);

                // A first upload goes out with the record VRChat handed back
                // when the SDK reserved the id, not the one composed here,
                // and that one is private. Send ours once the avatar exists.
                var live = await VRCApi.GetAvatar(assigned, true);
                if (Check(live).Count > 0) live = await SendRecord(instance, assigned);
                var drift = Check(live);
                return "Uploaded " + slug + " as " + assigned + " (" + report.performanceRank + ")." +
                       (drift.Count == 0
                           ? " VRChat's record matches the upload policy."
                           : " But VRChat's record does not match the upload policy:\n  " + string.Join("\n  ", drift));
            }
            finally
            {
                Running = false;
                UnityEngine.Object.DestroyImmediate(instance);
            }
        }

        /// <summary>
        /// Builds a variant and composes its thumbnail from the result,
        /// without uploading anything.
        /// </summary>
        /// <returns>Path of the thumbnail PNG.</returns>
        public static string Thumbnail(string slug)
        {
            return Thumbnail(slug, out _);
        }

        private static string Thumbnail(string slug, out BuildReport report)
        {
            report = CassBuild.Measure(slug, out var built);
            try
            {
                report.cutout = Path.GetFullPath(CassThumbnail.RenderCutout(built, Path.Combine(CassThumbnail.Folder, slug + "-cutout.png")));
                return CassThumbnail.Compose(report);
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(built);
                AvatarProcessor.CleanTemporaryAssets();
            }
        }

        private static VRCAvatar Compose(GameObject avatar, VRCAvatar existing, out List<string> dropped)
        {
            var profile = avatar.GetComponent<AvatarUploadProfile>();
            if (profile == null)
                throw new InvalidOperationException(avatar.name + " has no Avatar Upload Profile; only variant prefabs can be uploaded.");

            var record = existing;
            record.Name = profile.avatarName;
            record.Description = profile.ComposeDescription();
            // Tags VRChat itself attached (system_, admin_) are not ours to drop.
            var kept = (existing.Tags ?? new List<string>())
                .Where(tag => !tag.StartsWith(Wirenook.Assets.Core.FeatureTags.Prefix, StringComparison.Ordinal));
            record.Tags = CassBuild.ComposeTags(avatar, out dropped).Concat(kept).Distinct().ToList();
            record.ReleaseStatus = new UploadPolicy().ReleaseStatus;
            return record;
        }

        public static List<string> Check(VRCAvatar record)
        {
            return UploadGuard.Check(new UploadPolicy(), record.Name, record.Description, record.Tags, record.ReleaseStatus);
        }

        private static string Blueprint(GameObject avatar)
        {
            var pipeline = avatar.GetComponent<PipelineManager>();
            return pipeline != null ? pipeline.blueprintId : "";
        }

        private static void SaveBlueprint(string slug, string blueprint)
        {
            var path = CassPrefabs.VariantPath(slug);
            var root = PrefabUtility.LoadPrefabContents(path);
            try
            {
                root.GetComponent<PipelineManager>().blueprintId = blueprint;
                PrefabUtility.SaveAsPrefabAsset(root, path);
            }
            finally
            {
                PrefabUtility.UnloadPrefabContents(root);
            }
        }
    }

    /// <summary>
    /// The same policy for uploads made by hand from the SDK panel. It reads
    /// what the panel is about to send and cancels the upload if a variant of
    /// this avatar would go out without its source link, required tags or
    /// public visibility. Deliberately easy to get around: delete the upload
    /// profile from the avatar, or change the policy.
    /// </summary>
    [InitializeOnLoad]
    public static class CassUploadPanelHook
    {
        static CassUploadPanelHook()
        {
            VRCSdkControlPanel.OnSdkPanelEnable += (sender, arguments) => Attach();
            Attach();
        }

        private static void Attach()
        {
            if (!VRCSdkControlPanel.TryGetBuilder<IVRCSdkAvatarBuilderApi>(out var builder)) return;
            builder.OnSdkUploadStart -= OnUploadStart;
            builder.OnSdkUploadStart += OnUploadStart;
        }

        private static void OnUploadStart(object sender, EventArgs arguments)
        {
            if (CassUpload.Running) return;
            if (!(sender is IVRCSdkAvatarBuilderApi builder)) return;
            var avatar = builder.SelectedAvatar;
            if (avatar == null || avatar.GetComponent<AvatarUploadProfile>() == null) return;

            // The panel keeps the pending record private; if a future SDK
            // renames it, say so and step aside rather than block uploads.
            var field = sender.GetType().GetField("_avatarData", BindingFlags.Instance | BindingFlags.NonPublic);
            if (field == null || !(field.GetValue(sender) is VRCAvatar pending))
            {
                Debug.LogWarning("[cass] Could not read the SDK panel's pending upload; the upload policy was not checked.");
                return;
            }

            var problems = CassUpload.Check(pending);
            if (problems.Count == 0) return;

            builder.CancelUpload();
            var message = "This upload was cancelled because it breaks the avatar's upload policy:\n\n  " +
                          string.Join("\n  ", problems) +
                          "\n\nUse Tools > Wirenook > Cass > Upload to fill these in automatically.";
            Debug.LogError("[cass] " + message);
            EditorApplication.delayCall += () => EditorUtility.DisplayDialog("Upload cancelled", message, "OK");
        }
    }
}
