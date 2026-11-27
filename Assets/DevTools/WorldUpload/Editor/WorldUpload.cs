using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Net;
using System.Reflection;
using System.Threading.Tasks;
using UnityEditor;
using UnityEngine;
using VRC.Core;
using VRC.SDKBase.Editor.Api;

namespace Wirenook.DevTools
{
    /// <summary>
    /// Sends a world built elsewhere to VRChat from this editor, which is signed in.
    ///
    /// The wirenook.net world (modules/wirenook-world) is a Unity project of its own that is only
    /// ever run in batch mode, where nobody is signed in. Its build leaves a bundle and an
    /// upload.json (scripts/world.sh upload there); this reads that file and makes the same calls
    /// the Worlds SDK's builder makes after a build: VRCApi.CreateNewWorld the first time,
    /// VRCApi.UpdateWorldBundle after it. Both projects are on the same Unity and SDK version.
    /// VRCApi labels what it sends with the editor's own platform, so a bundle for another one
    /// goes through UpdateBundleFor, and a world's first upload has to be for this editor's.
    ///
    /// The SDK's builder asks whoever uploads to confirm they hold the rights to the content, per
    /// content id and editor session. Nothing here answers that: Send refuses an id that has no
    /// agreement recorded in this session.
    /// </summary>
    public static class WorldUpload
    {
        [Serializable]
        private sealed class Manifest
        {
            public string id;
            public string name;
            public string description;
            public string[] tags;
            public int capacity;
            public int recommendedCapacity;
            public string platform;
            public string unityVersion;
            public string bundle;
            public string signature;
            public string image;
        }

        /// <summary>Uploads the build an upload.json describes, as a new world or as a new version of the one that holds its id.</summary>
        public static async Task<string> Send(string manifestPath)
        {
            var manifest = JsonUtility.FromJson<Manifest>(File.ReadAllText(manifestPath));
            if (string.IsNullOrEmpty(manifest.id) || !manifest.id.StartsWith("wrld_", StringComparison.Ordinal))
                throw new InvalidOperationException(manifestPath + " names no world id");
            if (!File.Exists(manifest.bundle)) throw new InvalidOperationException("no bundle at " + manifest.bundle);
            if (string.IsNullOrEmpty(manifest.signature)) throw new InvalidOperationException(manifestPath + " has no world signature");

            await SignedIn();
            if (!APIUser.CurrentUser.canPublishWorlds)
                throw new InvalidOperationException("the account signed in here is not allowed to upload worlds");
            var here = VRC.Tools.Platform == manifest.platform;
            if (Application.unityVersion != manifest.unityVersion)
                throw new InvalidOperationException("the bundle was built with Unity " + manifest.unityVersion + " and this editor is " + Application.unityVersion);

            var has = typeof(VRC.SDKBase.VRCCopyrightAgreement).GetMethod("HasAgreement", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
            if (has == null) throw new InvalidOperationException("this SDK does not say whether a rights agreement is recorded");
            if (!await (Task<bool>)has.Invoke(null, new object[] { manifest.id }))
                throw new InvalidOperationException("no rights agreement is recorded for " + manifest.id + " in this session of the editor");

            VRCWorld existing = default;
            var exists = false;
            try
            {
                existing = await VRCApi.GetWorld(manifest.id, true);
                exists = !string.IsNullOrEmpty(existing.ID);
            }
            catch (ApiErrorException error) when (error.StatusCode == HttpStatusCode.NotFound)
            {
            }

            if (exists && existing.AuthorId != APIUser.CurrentUser.id)
                throw new InvalidOperationException(manifest.id + " belongs to another account");

            var steps = new List<string>();
            void Progress(string status, float amount)
            {
                if (steps.Count == 0 || steps[steps.Count - 1] != status) steps.Add(status);
            }

            VRCWorld record = exists ? existing : new VRCWorld { ID = manifest.id };
            record.Name = manifest.name;
            record.Description = manifest.description;
            record.Tags = (manifest.tags ?? new string[0]).ToList();
            record.Capacity = manifest.capacity;
            record.RecommendedCapacity = manifest.recommendedCapacity;
            record.UdonProducts = record.UdonProducts ?? new List<string>();
            record.PreviewYoutubeId = record.PreviewYoutubeId ?? "";

            string done;
            if (!exists && !here)
                throw new InvalidOperationException("the world does not exist yet, the bundle is for " + manifest.platform + " and this editor is on " +
                                                    VRC.Tools.Platform + "; send the build for this editor's platform first");

            if (!exists)
            {
                if (!File.Exists(manifest.image)) throw new InvalidOperationException("a new world needs a picture, and there is none at " + manifest.image);
                await VRCApi.CreateNewWorld(manifest.id, record, manifest.bundle, Cropped(manifest.image), manifest.signature, Progress);
                done = "created";
            }
            else
            {
                if (here) await VRCApi.UpdateWorldBundle(manifest.id, record, manifest.bundle, manifest.signature, Progress);
                else await UpdateBundleFor(manifest.platform, record, manifest.bundle, manifest.signature, Progress);
                var live = await VRCApi.GetWorld(manifest.id, true);
                live.Name = manifest.name;
                live.Description = manifest.description;
                live.Tags = record.Tags;
                live.Capacity = manifest.capacity;
                live.RecommendedCapacity = manifest.recommendedCapacity;
                await VRCApi.UpdateWorldInfo(manifest.id, live);
                done = "updated";

                if (File.Exists(manifest.image))
                {
                    var cropped = Cropped(manifest.image);
                    if (!await Holds(live.ImageUrl, cropped))
                    {
                        await VRCApi.UpdateWorldImage(manifest.id, live, cropped, Progress);
                        done += ", with a new picture";
                    }
                }
            }

            return done + " for " + manifest.platform + "\n" + await Live(manifest.id);
        }

        /// <summary>What VRChat holds for a world id.</summary>
        public static async Task<string> Live(string id)
        {
            await SignedIn();
            var world = await VRCApi.GetWorld(id, true);
            var packages = (world.UnityPackages ?? new List<VRCUnityPackage>())
                .GroupBy(package => package.Platform)
                .Select(group => group.Key + " v" + group.Max(package => package.AssetVersion) + " (" + group.Max(package => package.CreatedAt).ToString("u") + ")");
            return "id: " + world.ID + "\n" +
                   "name: " + world.Name + "\n" +
                   "release: " + world.ReleaseStatus + "\n" +
                   "version: " + world.Version + "\n" +
                   "platforms: " + string.Join(", ", packages) + "\n" +
                   "capacity: " + world.Capacity + " (recommended " + world.RecommendedCapacity + ")\n" +
                   "tags: " + string.Join(", ", world.Tags ?? new List<string>()) + "\n" +
                   "updated: " + world.UpdatedAt.ToString("u") + "\n" +
                   "description: " + world.Description;
        }

        /// <summary>Whether VRChat would let this world be published to Community Labs now.</summary>
        public static async Task<string> CanPublish(string id)
        {
            await SignedIn();
            return (await VRCApi.GetCanPublishWorld(id)) ? "yes" : "no";
        }

        /// <summary>Publishes a world to Community Labs, which is what making a world public is.</summary>
        public static async Task<string> Publish(string id)
        {
            await SignedIn();
            if (!await VRCApi.GetCanPublishWorld(id))
                throw new InvalidOperationException("VRChat does not let this account publish " + id + " now");
            var answer = await VRCApi.PublishWorld(id);
            return (answer == null ? "" : answer.ToString() + "\n") + await Live(id);
        }

        /// <summary>
        /// VRCApi.UpdateWorldBundle for a platform other than this editor's. The SDK's own method
        /// labels the file and the request with the editor's platform and has no way to be told
        /// another, so this makes its two requests with the bundle's: the file (through the SDK's
        /// uploader, which is private) and the world's new asset.
        /// </summary>
        private static async Task UpdateBundleFor(string platform, VRCWorld data, string bundle, string signature, Action<string, float> progress)
        {
            var upload = typeof(VRCApi).GetMethod("UploadFile", BindingFlags.Static | BindingFlags.NonPublic);
            if (upload == null || upload.GetParameters().Length != 6)
                throw new InvalidOperationException("this SDK's VRCApi.UploadFile is not the one this was written against");

            var fileName = "World - " + data.Name + " - Asset bundle - " + Application.unityVersion + "_" + ApiWorld.VERSION.ApiVersion +
                           "_" + platform + "_" + API.GetServerEnvironmentForApiUrl();
            var current = data.GetLatestAssetUrlForPlatform(platform);
            var fileId = string.IsNullOrWhiteSpace(current) ? "" : ApiFile.ParseFileIdFromFileAPIUrl(current);
            var url = await (Task<string>)upload.Invoke(null, new object[]
            {
                bundle, fileId, fileName, false, progress, default(System.Threading.CancellationToken),
            });
            if (string.IsNullOrWhiteSpace(url)) throw new InvalidOperationException("VRChat gave no address for the uploaded bundle");

            var request = new Dictionary<string, object>
            {
                { "name", data.Name },
                { "assetUrl", url },
                { "platform", platform },
                { "unityVersion", VRC.Tools.UnityVersion.ToString() },
                { "assetVersion", 4 },
                { "udonProducts", data.UdonProducts },
                { "worldSignature", signature },
            };
            await VRCApi.Put<object, VRCWorld>("worlds/" + data.ID, request);
        }

        private static async Task SignedIn()
        {
            if (APIUser.IsLoggedIn) return;
            EditorApplication.ExecuteMenuItem("VRChat SDK/Show Control Panel");
            for (var waited = 0; waited < 40 && !APIUser.IsLoggedIn; waited++) await Task.Delay(500);
            if (!APIUser.IsLoggedIn)
                throw new InvalidOperationException("Sign in to VRChat in the SDK control panel (it is open now), then run this again.");
        }

        /// <summary>The picture as the SDK's builder would send it: cropped to four by three. Its cropping is internal.</summary>
        private static string Cropped(string image)
        {
            var crop = typeof(VRC.SDKBase.VRC_EditorTools).GetMethod("CropImage", BindingFlags.Static | BindingFlags.NonPublic | BindingFlags.Public);
            if (crop == null || crop.GetParameters().Length != 6) return image;
            var sent = crop.Invoke(null, new object[] { image, 800f, 600f, true, false, false }) as string;
            return string.IsNullOrEmpty(sent) || !File.Exists(sent) ? image : sent;
        }

        /// <summary>Whether VRChat already holds exactly this picture; it refuses a file identical to the one it has.</summary>
        private static async Task<bool> Holds(string imageUrl, string picture)
        {
            if (string.IsNullOrEmpty(imageUrl)) return false;
            string hash;
            using (var md5 = System.Security.Cryptography.MD5.Create())
                hash = Convert.ToBase64String(md5.ComputeHash(File.ReadAllBytes(picture)));
            var file = await VRCApi.Get<VRCFile>("file/" + ApiFile.ParseFileIdFromFileAPIUrl(imageUrl), forceRefresh: true);
            var latest = file.GetLatestVersion();
            return latest >= 0 && file.Versions[latest]?.File?.MD5 == hash;
        }
    }
}
