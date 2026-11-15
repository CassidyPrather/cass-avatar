// Describes a loaded type's public and serialized surface through the bridge:
//
//     scripts/unity-bridge.py invoke Wirenook.DevTools.Reflect.Describe VRC.SDK3.Avatars.Components.VRCAvatarDescriptor
//
// The VRChat SDK ships as compiled assemblies with thin documentation, so the
// quickest reliable answer to "what is this field called" is to ask the editor.
using System;
using System.Linq;
using System.Reflection;
using System.Text;

namespace Wirenook.DevTools
{
    public static class Reflect
    {
        public static string Describe(string typeName)
        {
            var type = Find(typeName);
            if (type == null) return "type not found: " + typeName;

            const BindingFlags flags =
                BindingFlags.Instance | BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic |
                BindingFlags.DeclaredOnly;
            var text = new StringBuilder();
            text.AppendLine(type.FullName + " : " + type.BaseType?.FullName + "  [" + type.Assembly.GetName().Name + "]");

            if (type.IsEnum)
            {
                foreach (var name in Enum.GetNames(type))
                    text.AppendLine("  " + name + " = " + Convert.ToInt64(Enum.Parse(type, name)));
                return text.ToString();
            }

            foreach (var field in type.GetFields(flags))
            {
                if (field.Name.Contains("k__BackingField")) continue;
                var access = field.IsPublic ? "public" : "private";
                text.AppendLine("  field " + access + (field.IsStatic ? " static " : " ") + Name(field.FieldType) + " " + field.Name);
            }

            foreach (var property in type.GetProperties(flags))
                text.AppendLine("  prop " + Name(property.PropertyType) + " " + property.Name);

            foreach (var method in type.GetMethods(flags).Where(m => !m.IsSpecialName && (m.IsPublic || m.IsAssembly)))
            {
                var parameters = string.Join(", ", method.GetParameters().Select(p => Name(p.ParameterType) + " " + p.Name));
                text.AppendLine("  method " + (method.IsPublic ? "public" : "internal") + (method.IsStatic ? " static " : " ") +
                                Name(method.ReturnType) + " " + method.Name + "(" + parameters + ")");
            }

            foreach (var nested in type.GetNestedTypes(flags))
                text.AppendLine("  nested " + (nested.IsEnum ? "enum " : "type ") + nested.FullName);

            return text.ToString();
        }

        /// <summary>Lists loaded types whose full name contains the given text.</summary>
        public static string Search(string fragment)
        {
            var hits = AppDomain.CurrentDomain.GetAssemblies()
                .SelectMany(SafeTypes)
                .Where(t => t.FullName != null && t.FullName.IndexOf(fragment, StringComparison.OrdinalIgnoreCase) >= 0)
                .Select(t => t.FullName + "  [" + t.Assembly.GetName().Name + "]")
                .OrderBy(n => n)
                .Take(120);
            return string.Join("\n", hits);
        }

        /// <summary>
        /// Lists a component type's serialized properties with their default
        /// values: the names SerializedObject and animation curves use, which
        /// are not always the C# member names.
        /// </summary>
        public static string Serialized(string typeName)
        {
            var type = Find(typeName);
            if (type == null) return "type not found: " + typeName;
            var holder = new UnityEngine.GameObject("Reflect") { hideFlags = UnityEngine.HideFlags.HideAndDontSave };
            try
            {
                var component = holder.AddComponent(type);
                var text = new StringBuilder();
                var property = new UnityEditor.SerializedObject(component).GetIterator();
                var enterChildren = true;
                while (property.NextVisible(enterChildren))
                {
                    enterChildren = property.propertyType == UnityEditor.SerializedPropertyType.Generic && property.depth < 1;
                    var value = "";
                    switch (property.propertyType)
                    {
                        case UnityEditor.SerializedPropertyType.Boolean: value = property.boolValue.ToString(); break;
                        case UnityEditor.SerializedPropertyType.Integer: value = property.intValue.ToString(); break;
                        case UnityEditor.SerializedPropertyType.Float: value = property.floatValue.ToString(); break;
                        case UnityEditor.SerializedPropertyType.String: value = "\"" + property.stringValue + "\""; break;
                        case UnityEditor.SerializedPropertyType.Enum:
                            value = property.enumValueIndex + " of [" + string.Join(", ", property.enumNames) + "]";
                            break;
                        case UnityEditor.SerializedPropertyType.Vector3: value = property.vector3Value.ToString(); break;
                    }

                    text.AppendLine(new string(' ', property.depth * 2) + property.propertyPath + " : " + property.propertyType + " " + value);
                }

                return text.ToString();
            }
            finally
            {
                UnityEngine.Object.DestroyImmediate(holder);
            }
        }

        /// <summary>
        /// Lists an asset's transform hierarchy with local position, rotation
        /// and scale, and each renderer's world bounds: how a model actually
        /// arrived after import.
        /// </summary>
        public static string Hierarchy(string assetPath)
        {
            var asset = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.GameObject>(assetPath);
            if (asset == null) return "no GameObject asset at " + assetPath;
            var text = new StringBuilder();
            foreach (var transform in asset.GetComponentsInChildren<UnityEngine.Transform>(true).Take(120))
            {
                var depth = 0;
                for (var parent = transform.parent; parent != null; parent = parent.parent) depth++;
                var line = new string(' ', depth * 2) + transform.name +
                           "  pos " + transform.localPosition.ToString("0.###") +
                           "  rot " + transform.localEulerAngles.ToString("0.#") +
                           "  scale " + transform.localScale.ToString("0.###");
                var renderer = transform.GetComponent<UnityEngine.Renderer>();
                if (renderer != null)
                {
                    line += "  [" + renderer.GetType().Name + " bounds centre " + renderer.bounds.center.ToString("0.###") +
                            " size " + renderer.bounds.size.ToString("0.###") + "]";
                }

                text.AppendLine(line);
            }

            return text.ToString();
        }

        /// <summary>
        /// Reports, for a mesh inside a model asset, how many blendshapes it
        /// has and how far each of the first few (or those containing
        /// <paramref name="filter"/>) moves its vertices.
        /// </summary>
        public static string Blendshapes(string assetPath, string meshObject, string filter)
        {
            var asset = UnityEditor.AssetDatabase.LoadAssetAtPath<UnityEngine.GameObject>(assetPath);
            if (asset == null) return "no GameObject asset at " + assetPath;
            var renderer = asset.GetComponentsInChildren<UnityEngine.SkinnedMeshRenderer>(true).FirstOrDefault(r => r.name == meshObject);
            if (renderer == null) return "no skinned mesh named " + meshObject;
            var mesh = renderer.sharedMesh;
            var text = new StringBuilder();
            text.AppendLine(mesh.blendShapeCount + " blendshapes, " + mesh.vertexCount + " vertices");
            var deltas = new UnityEngine.Vector3[mesh.vertexCount];
            var shown = 0;
            for (var i = 0; i < mesh.blendShapeCount && shown < 12; i++)
            {
                var name = mesh.GetBlendShapeName(i);
                if (!string.IsNullOrEmpty(filter) && name.IndexOf(filter, StringComparison.OrdinalIgnoreCase) < 0) continue;
                var frames = mesh.GetBlendShapeFrameCount(i);
                mesh.GetBlendShapeFrameVertices(i, frames - 1, deltas, null, null);
                var moved = deltas.Count(delta => delta.sqrMagnitude > 1e-12f);
                var largest = deltas.Max(delta => delta.magnitude);
                text.AppendLine("  " + name + ": frames " + frames + ", full weight " + mesh.GetBlendShapeFrameWeight(i, frames - 1) +
                                ", moves " + moved + " vertices, largest " + largest.ToString("0.#####") + " m");
                shown++;
            }

            return text.ToString();
        }

        /// <summary>The value of a static field or property, for constants the SDK does not document.</summary>
        public static string Static(string typeName, string member)
        {
            var type = Find(typeName);
            if (type == null) return "type not found: " + typeName;
            const BindingFlags flags = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
            var field = type.GetField(member, flags);
            if (field != null) return field.GetValue(null)?.ToString();
            var property = type.GetProperty(member, flags);
            return property != null ? property.GetValue(null)?.ToString() : "no static member " + member;
        }

        /// <summary>Lists the open scenes and their root objects.</summary>
        public static string Scenes()
        {
            var text = new StringBuilder();
            for (var i = 0; i < UnityEngine.SceneManagement.SceneManager.sceneCount; i++)
            {
                var scene = UnityEngine.SceneManagement.SceneManager.GetSceneAt(i);
                text.AppendLine((string.IsNullOrEmpty(scene.path) ? "(untitled)" : scene.path) +
                                (scene.isDirty ? " [unsaved changes]" : "") +
                                (scene == UnityEngine.SceneManagement.SceneManager.GetActiveScene() ? " [active]" : ""));
                foreach (var root in scene.GetRootGameObjects())
                    text.AppendLine("  " + root.name + " (" + root.GetComponentsInChildren<UnityEngine.Transform>(true).Length + " objects)");
            }

            return text.ToString();
        }

        private static Type Find(string typeName)
        {
            return AppDomain.CurrentDomain.GetAssemblies()
                .Select(a => a.GetType(typeName, false))
                .FirstOrDefault(t => t != null);
        }

        private static Type[] SafeTypes(Assembly assembly)
        {
            try
            {
                return assembly.GetTypes();
            }
            catch (ReflectionTypeLoadException e)
            {
                return e.Types.Where(t => t != null).ToArray();
            }
        }

        private static string Name(Type type)
        {
            if (!type.IsGenericType) return type.Name;
            var arguments = string.Join(", ", type.GetGenericArguments().Select(Name));
            return type.Name.Split('`')[0] + "<" + arguments + ">";
        }
    }
}
