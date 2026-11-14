using UnityEngine;

namespace Wirenook.Validation
{
    /// <summary>
    /// One lighting condition in the validation scene: the lights parented
    /// under this object plus the ambient light that goes with them. Ambient
    /// light is a scene-wide setting, so it is stored here and applied when
    /// the condition is switched on.
    /// </summary>
    public sealed class LightingCondition : MonoBehaviour
    {
        [ColorUsage(false, true)]
        public Color ambient = Color.black;

        [TextArea]
        public string looksFor;

        /// <summary>Makes this the only active condition among its siblings.</summary>
        public void Activate()
        {
            foreach (Transform sibling in transform.parent)
                sibling.gameObject.SetActive(sibling == transform);
            RenderSettings.ambientMode = UnityEngine.Rendering.AmbientMode.Flat;
            RenderSettings.ambientLight = ambient;
        }
    }
}
