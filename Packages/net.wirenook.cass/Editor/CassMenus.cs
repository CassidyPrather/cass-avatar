using System.Collections.Generic;
using System.Linq;
using UnityEditor;
using UnityEngine;
using VRC.SDK3.Avatars.ScriptableObjects;
using Wirenook.Assets.Editor;

namespace Wirenook.Cass.Editor
{
    /// <summary>
    /// Generates the base avatar's expression parameters and radial menu.
    /// Optional features bring their own through Modular Avatar; only what
    /// every variant has lives here.
    /// </summary>
    public static class CassMenus
    {
        public const string ParametersPath = CassSpec.GeneratedFolder + "/cass-parameters.asset";
        public const string MenuPath = CassSpec.GeneratedFolder + "/cass-menu.asset";
        public const string OutfitMenuPath = CassSpec.GeneratedFolder + "/cass-menu-outfit.asset";

        /// <summary>
        /// The "Outfit" entry on its own. It is added to the menu at build
        /// time, from an object mobile builds leave out: the garment toggles
        /// hide UV tiles, which no mobile shader can do.
        /// </summary>
        public const string OutfitEntryPath = CassSpec.GeneratedFolder + "/cass-menu-outfit-entry.asset";

        public static void Rebuild()
        {
            var tiles = CassSpec.Tiles();
            // One menu entry per switch that is offered: it has a label, and
            // taking its garment off cannot leave the body bare where it has
            // nothing else to wear. Tiles that share a parameter
            // (alternatives) are one switch.
            var toggles = tiles.Offered();
            var offered = new HashSet<string>(toggles.Select(tile => tile.Toggle.Parameter));

            var parameters = AssetFolders.LoadOrCreate(ParametersPath, ScriptableObject.CreateInstance<VRCExpressionParameters>);
            var list = new List<VRCExpressionParameters.Parameter> { Bool(CassFx.TrackingEnabled, true) };
            // A switch that is not offered is not synced either: its
            // parameter exists in the animator alone and stays at rest.
            list.AddRange(tiles.Defaults().Where(parameter => offered.Contains(parameter.Parameter))
                .Select(parameter => Bool(parameter.Parameter, parameter.Value)));
            parameters.parameters = list.ToArray();
            EditorUtility.SetDirty(parameters);

            var outfit = AssetFolders.LoadOrCreate(OutfitMenuPath, ScriptableObject.CreateInstance<VRCExpressionsMenu>);
            outfit.controls = toggles.Select(tile => Toggle(tile.Toggle.Label, tile.Toggle.Icon, tile.Toggle.Parameter)).ToList();
            EditorUtility.SetDirty(outfit);

            var entry = AssetFolders.LoadOrCreate(OutfitEntryPath, ScriptableObject.CreateInstance<VRCExpressionsMenu>);
            entry.controls = new List<VRCExpressionsMenu.Control>
            {
                new VRCExpressionsMenu.Control
                {
                    name = "Outfit",
                    icon = WirenookIcons.Get("outfit"),
                    type = VRCExpressionsMenu.Control.ControlType.SubMenu,
                    subMenu = outfit,
                },
            };
            EditorUtility.SetDirty(entry);

            var menu = AssetFolders.LoadOrCreate(MenuPath, ScriptableObject.CreateInstance<VRCExpressionsMenu>);
            menu.controls = new List<VRCExpressionsMenu.Control>
            {
                Toggle("Face Tracking", "face-tracking", CassFx.TrackingEnabled),
            };
            EditorUtility.SetDirty(menu);

            AssetDatabase.SaveAssets();
        }

        /// <summary>A synced, saved switch: it survives avatar reloads and world changes.</summary>
        private static VRCExpressionParameters.Parameter Bool(string name, bool defaultValue)
        {
            return new VRCExpressionParameters.Parameter
            {
                name = name,
                valueType = VRCExpressionParameters.ValueType.Bool,
                defaultValue = defaultValue ? 1f : 0f,
                saved = true,
                networkSynced = true,
            };
        }

        private static VRCExpressionsMenu.Control Toggle(string label, string icon, string parameter)
        {
            return new VRCExpressionsMenu.Control
            {
                name = label,
                icon = WirenookIcons.Get(icon),
                type = VRCExpressionsMenu.Control.ControlType.Toggle,
                parameter = new VRCExpressionsMenu.Control.Parameter { name = parameter },
                value = 1f,
            };
        }
    }
}
