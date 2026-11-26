using System;
using System.Linq;
using nadena.dev.ndmf;
using UnityEditor;
using UnityEngine;
using Wirenook.Assets.Editor;
using Wirenook.Bot.Editor;

[assembly: ExportsPlugin(typeof(BotBuildPlugin))]

namespace Wirenook.Bot.Editor
{
    /// <summary>
    /// The bot's own step in the non-destructive build.
    ///
    /// On Android and iOS the projected ears and tail are drawn with the
    /// material of everything else. No mobile shader adds light to what is
    /// behind it, so the hologram could only be a second material doing the
    /// first one's work, and a third material slot is what takes the avatar
    /// from Medium to Poor there. Their drawing is in the same atlas, so on
    /// mobile they are solid where on PC they glow.
    /// </summary>
    public sealed class BotBuildPlugin : Plugin<BotBuildPlugin>
    {
        public override string QualifiedName => "net.wirenook.bot";
        public override string DisplayName => "Wirenook Bot";

        protected override void Configure()
        {
            // Before Modular Avatar and Avatar Optimizer, which then find one material where there were two.
            InPhase(BuildPhase.Resolving).BeforePlugin("nadena.dev.modular-avatar").Run("Draw the hologram solid on mobile", context =>
            {
                if (!WirenookPlatform.IsMobile) return;
                var solid = AssetDatabase.LoadAssetAtPath<Material>(BotBuild.MaterialPath("bot"));
                var hologram = AssetDatabase.LoadAssetAtPath<Material>(BotBuild.MaterialPath("bot-holo"));
                if (solid == null || hologram == null) return;
                foreach (var renderer in context.AvatarRootObject.GetComponentsInChildren<Renderer>(true))
                {
                    if (!renderer.sharedMaterials.Contains(hologram)) continue;
                    renderer.sharedMaterials = renderer.sharedMaterials.Select(material => material == hologram ? solid : material).ToArray();
                }
            });
        }
    }
}
