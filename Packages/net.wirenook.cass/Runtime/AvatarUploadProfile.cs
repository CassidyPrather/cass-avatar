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

        [TextArea(3, 8)]
        [Tooltip("The description. It has to say where the avatar's source can be found.")]
        public string description = "";

        [Tooltip("Tags beyond the required ones and those the variant's features contribute.")]
        public List<string> extraTags = new List<string>();

        [Tooltip("One line for each asset the variant carries that is not part of the avatar's source, such as a bought prop: " +
                 "\"name by author\". Any entry here makes the upload private and adds the credits to the description.")]
        public List<string> carries = new List<string>();

        /// <summary>The description as it is sent to VRChat.</summary>
        public string ComposeDescription()
        {
            var text = (description ?? "").Trim();
            if (carries.Count > 0) text += " Carries, not from that source or under its licence: " + string.Join("; ", carries) + ".";
            return text;
        }

        /// <summary>What an upload of this variant has to satisfy.</summary>
        public Core.UploadPolicy Policy()
        {
            return carries.Count > 0 ? Core.UploadPolicy.Carrying(carries) : new Core.UploadPolicy();
        }
    }
}
