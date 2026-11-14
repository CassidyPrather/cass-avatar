using System.Collections.Generic;
using UnityEngine;
using Wirenook.Assets;

namespace Wirenook.Cass
{
    /// <summary>
    /// What an upload variant is called and how it describes itself on
    /// VRChat. It sits on the root of each variant prefab; the uploader reads
    /// it instead of anyone typing into the SDK panel, so a variant uploads
    /// the same way every time. Stripped from the upload itself.
    /// </summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("Wirenook/Avatar Upload Profile")]
    public sealed class AvatarUploadProfile : MonoBehaviour, IWirenookEditorOnly
    {
        [Tooltip("The avatar's name on VRChat: \"cass\", or \"cass-\" plus a short variant slug.")]
        public string avatarName = "cass";

        [Tooltip("One line saying what sets this variant apart; shown first in the description.")]
        public string summary = "";

        [TextArea(3, 8)]
        [Tooltip("The rest of the description. It has to say where the avatar's source can be found.")]
        public string description = "";

        [Tooltip("Tags beyond the required ones and those the variant's features contribute.")]
        public List<string> extraTags = new List<string>();

        /// <summary>The description as it is sent to VRChat.</summary>
        public string ComposeDescription()
        {
            var first = (summary ?? "").Trim();
            var rest = (description ?? "").Trim();
            if (first.Length == 0) return rest;
            if (rest.Length == 0) return first;
            return first + " " + rest;
        }
    }
}
