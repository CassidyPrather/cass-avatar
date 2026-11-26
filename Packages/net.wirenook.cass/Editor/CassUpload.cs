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
using Wirenook.Assets.Editor;
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
                var problems = Check(record, instance);
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
            var variant = CassBuild.LoadVariant(slug);
            var pipeline = variant.GetComponent<PipelineManager>();
            var blueprint = pipeline != null ? pipeline.blueprintId : "";
            if (string.IsNullOrEmpty(blueprint)) return slug + " has not been uploaded.";

            await SignedIn();
            var live = await VRCApi.GetAvatar(blueprint, true);
            var problems = Check(live, variant);
            return "id: " + live.ID + "\n" +
                   "name: " + live.Name + "\n" +
                   "description: " + live.Description + "\n" +
                   "tags: " + string.Join(", ", live.Tags ?? new List<string>()) + "\n" +
                   "release: " + live.ReleaseStatus + "\n" +
                   "platforms: " + string.Join(", ", (live.UnityPackages ?? new List<VRCUnityPackage>())
                       .Select(package => package.Platform).Distinct().OrderBy(platform => platform)) + "\n" +
                   (problems.Count == 0 ? "policy: ok" : "policy: FAILS\n  " + string.Join("\n  ", problems));
        }

        /// <summary>
        /// Takes a deprecated variant's avatar down from VRChat. It is gone
        /// for good: the id cannot be had again, and anyone who had the
        /// avatar as a favourite or was wearing a clone's source loses it.
        /// Only a variant that Spec/variants.json lists under `deprecated`
        /// can be retired, so that what replaced it is written down first.
        /// </summary>
        public static async Task<string> Retire(string slug)
        {
            var spec = CassSpec.Variants();
            if (spec.Variants.Any(variant => variant.Slug == slug))
                throw new InvalidOperationException(slug + " is still a variant. Move it to `deprecated` in Spec/variants.json first.");
            var gone = spec.Deprecated.FirstOrDefault(variant => variant.Slug == slug)
                       ?? throw new InvalidOperationException("Spec/variants.json lists no deprecated variant named " + slug + ".");
            if (string.IsNullOrEmpty(gone.AvatarId)) return slug + " was never uploaded; there is nothing to take down.";
            if (spec.Variants.Any(variant => CassPrefabs.BlueprintOf(variant.Slug) == gone.AvatarId))
                throw new InvalidOperationException(slug + "'s avatar id is in use by a variant that is still made. Nothing was deleted.");

            await SignedIn();
            VRCAvatar live;
            try
            {
                live = await VRCApi.GetAvatar(gone.AvatarId, true);
            }
            catch (Exception error)
            {
                return slug + " (" + gone.AvatarId + ") is not on VRChat any more, or cannot be read: " + error.Message;
            }

            await VRCApi.DeleteAvatar(gone.AvatarId);
            return "Deleted " + slug + " (" + live.Name + ", " + gone.AvatarId + ") from VRChat." +
                   (string.IsNullOrEmpty(gone.ReplacedBy) ? "" : " What it carried is in " + gone.ReplacedBy + ".");
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
            var problems = Check(record, instance);
            if (problems.Count > 0)
                throw new InvalidOperationException("Refused by the upload policy:\n  " + string.Join("\n  ", problems));

            await VRCApi.UpdateAvatarInfo(blueprint, record);
            return await VRCApi.GetAvatar(blueprint, true);
        }

        /// <summary>
        /// Whether the picture VRChat holds for an avatar is exactly the one
        /// an upload would send. The SDK crops a thumbnail before sending it
        /// and VRChat compares hashes of what arrives, so this crops the same
        /// way first. The SDK keeps its cropping to itself, hence the
        /// reflection; when anything here cannot be worked out the answer is
        /// no, and the upload sends the picture as it always did.
        /// </summary>
        private static async Task<bool> HoldsThumbnail(VRCAvatar existing, string thumbnail)
        {
            if (string.IsNullOrEmpty(existing.ID) || string.IsNullOrEmpty(existing.ImageUrl)) return false;

            var crop = typeof(VRC.SDKBase.VRC_EditorTools).GetMethod("CropImage", BindingFlags.Static | BindingFlags.NonPublic);
            if (crop == null || crop.GetParameters().Length != 6) return false;
            var sent = crop.Invoke(null, new object[] { thumbnail, 800f, 600f, true, false, false }) as string;
            if (string.IsNullOrEmpty(sent) || !File.Exists(sent)) return false;

            string hash;
            using (var md5 = System.Security.Cryptography.MD5.Create())
                hash = Convert.ToBase64String(md5.ComputeHash(File.ReadAllBytes(sent)));

            var file = await VRCApi.Get<VRCFile>("file/" + ApiFile.ParseFileIdFromFileAPIUrl(existing.ImageUrl), forceRefresh: true);
            var latest = file.GetLatestVersion();
            return latest >= 0 && file.Versions[latest]?.File?.MD5 == hash;
        }

        /// <summary>Builds and uploads a variant. Needs an account signed in through the SDK control panel.</summary>
        public static async Task<string> Upload(string slug)
        {
            // The SDK builds for the editor's active target, whatever a build
            // has been told to pretend.
            WirenookPlatform.Pretend("");
            var platform = WirenookPlatform.Active;
            var spec = CassSpec.Variants().Variants.First(candidate => candidate.Slug == slug);
            if (!spec.Platforms.Contains(platform))
                throw new InvalidOperationException(slug + " is not built for " + WirenookPlatform.Name(platform) +
                                                    " (Spec/variants.json lists its platforms). Switch with scripts/cass.sh platform.");

            var builder = await SignedIn();

            // Uploading to an id replaces whatever avatar holds it.
            CassPrefabs.SeparateBlueprints();
            var sharing = CassPrefabs.SharesBlueprintWith(slug);
            if (sharing != null)
                throw new InvalidOperationException(
                    slug + " and " + sharing + " hold the same avatar id, so uploading one would replace the other. " +
                    "Clear the blueprint id on whichever variant prefab has not been uploaded.");

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

                var problems = Check(record, instance);
                if (problems.Count > 0)
                    throw new InvalidOperationException("Upload refused by the upload policy:\n  " + string.Join("\n  ", problems));

                // VRChat refuses a file identical to the one it holds, and the
                // SDK sends the picture before the bundle, so an unchanged
                // picture would stop the upload before the avatar itself
                // went out. Left out, VRChat keeps the picture it has.
                if (await HoldsThumbnail(existing, thumbnail)) thumbnail = null;

                await builder.BuildAndUpload(instance, record, thumbnail);

                // The SDK writes a newly reserved id onto the scene copy only;
                // keep it with the variant so the next upload updates the same avatar.
                var assigned = Blueprint(instance);
                if (assigned != blueprint) SaveBlueprint(slug, assigned);

                // A first upload goes out with the record VRChat handed back
                // when the SDK reserved the id, not the one composed here,
                // and that one is private. Send ours once the avatar exists.
                var live = await VRCApi.GetAvatar(assigned, true);
                if (Check(live, instance).Count > 0) live = await SendRecord(instance, assigned);
                var drift = Check(live, instance);
                return "Uploaded " + slug + " for " + WirenookPlatform.Name(platform) + " as " + assigned + " (" + report.performanceRank + ")." +
                       (drift.Count == 0
                           ? " VRChat's record matches the upload policy."
                           : " But VRChat's record does not match the upload policy:\n  " + string.Join("\n  ", drift));
            }
            finally
            {
                Running = false;
                UnityEngine.Object.DestroyImmediate(instance);
                Tidy(slug);
            }
        }

        /// <summary>
        /// Puts the open scene back the way it was before an upload. The SDK
        /// saves the scene while the copy it builds from is in it, so the
        /// file on disk keeps that copy even though it is destroyed here, and
        /// the next time the scene loads the copy stands in every picture
        /// taken there. This removes any copy still in the scene and saves
        /// the scene without it.
        /// </summary>
        /// <returns>How many copies were still in the scene.</returns>
        public static int Tidy(string slug)
        {
            var prefab = CassBuild.LoadVariant(slug);
            var scene = UnityEngine.SceneManagement.SceneManager.GetActiveScene();
            var leftovers = scene.GetRootGameObjects()
                .Where(root => PrefabUtility.GetCorrespondingObjectFromSource(root) == prefab)
                .ToList();
            foreach (var leftover in leftovers) UnityEngine.Object.DestroyImmediate(leftover);
            if (!string.IsNullOrEmpty(scene.path))
            {
                // The build framework keeps a hidden object of its own in every open
                // scene. Saved, it is a change to a committed file after every upload,
                // and putting the file back makes Unity stop and ask what to do about
                // a scene changed behind its back. It is kept out of the file instead.
                var passing = scene.GetRootGameObjects()
                    .Where(root => root.name.StartsWith("nadena.dev.ndmf", StringComparison.Ordinal))
                    .ToDictionary(root => root, root => root.hideFlags);
                foreach (var root in passing.Keys) root.hideFlags |= HideFlags.DontSaveInEditor;
                // Unity skips saving a scene it believes unchanged.
                UnityEditor.SceneManagement.EditorSceneManager.MarkSceneDirty(scene);
                UnityEditor.SceneManagement.EditorSceneManager.SaveScene(scene);
                foreach (var root in passing) root.Key.hideFlags = root.Value;
            }

            return leftovers.Count;
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
            record.ReleaseStatus = profile.Policy().ReleaseStatus;
            return record;
        }

        /// <param name="avatar">The variant the record is for; its profile says which policy applies.</param>
        public static List<string> Check(VRCAvatar record, GameObject avatar)
        {
            var profile = avatar != null ? avatar.GetComponent<AvatarUploadProfile>() : null;
            var policy = profile != null ? profile.Policy() : new UploadPolicy();
            return UploadGuard.Check(policy, record.Name, record.Description, record.Tags, record.ReleaseStatus);
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

            // Variants that extend this one have just inherited the new id.
            CassPrefabs.SeparateBlueprints();
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

            var problems = CassUpload.Check(pending, avatar.gameObject);
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
