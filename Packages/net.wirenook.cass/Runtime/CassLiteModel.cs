using UnityEngine;
using Wirenook.Assets;

namespace Wirenook.Cass
{
    /// <summary>
    /// On the root of a variant: build it from the low-polygon model
    /// (<c>BlenderExports/cass-lite.fbx</c>) on every platform. Android and
    /// iOS builds use that model whether or not this is present. The
    /// prefabs themselves always hold the full model; the meshes are
    /// exchanged on the copy the build works on. Stripped from the upload.
    /// </summary>
    [DisallowMultipleComponent]
    [AddComponentMenu("Wirenook/Cass Lite Model")]
    public sealed class CassLiteModel : MonoBehaviour, IWirenookEditorOnly
    {
    }
}
