using UnityEngine;
using Wirenook.Assets;

namespace Wirenook.Cass
{
    /// <summary>
    /// On the root of a variant: build it wearing another wardrobe. Blender
    /// exports each wardrobe as a model of its own on the same skeleton
    /// (<c>BlenderExports/cass-&lt;wardrobe&gt;.fbx</c>, and its
    /// <c>-lite</c>), with the same mesh names, bones, blendshapes and UV
    /// tiles, so the build can exchange the meshes by name exactly as it
    /// does for the low-polygon model. The prefabs themselves always hold
    /// the first wardrobe; the exchange is made on the copy the build works
    /// on. Stripped from the upload.
    /// </summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("Wirenook/Cass Wardrobe")]
    public sealed class CassWardrobe : MonoBehaviour, IWirenookEditorOnly
    {
        [Tooltip("The wardrobe's name as it appears in the export's file name, e.g. \"cyber\".")]
        public string wardrobe = "";
    }
}
