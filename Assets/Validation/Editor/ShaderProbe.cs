using System.Linq;
using System.Text;
using UnityEditor;
using UnityEngine;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Says whether a shader exists and compiled, and with what messages. A
    /// shader that fails to compile does not stop a refresh or a build; it
    /// draws magenta, or in a build nothing at all.
    /// </summary>
    public static class ShaderProbe
    {
        /// <returns>One line per shader: its name, pass count and any compiler messages.</returns>
        public static string Check(string names)
        {
            var report = new StringBuilder();
            foreach (var name in names.Split(';').Select(part => part.Trim()).Where(part => part.Length > 0))
            {
                var shader = Shader.Find(name);
                if (shader == null)
                {
                    report.AppendLine(name + ": NOT FOUND");
                    continue;
                }

                var messages = ShaderUtil.GetShaderMessages(shader);
                report.AppendLine(name + ": " + shader.passCount + " passes, " + (shader.isSupported ? "supported" : "NOT SUPPORTED") +
                                  ", " + messages.Count(message => message.severity == UnityEditor.Rendering.ShaderCompilerMessageSeverity.Error) + " errors, " +
                                  AssetDatabase.GetAssetPath(shader));
                foreach (var message in messages.Take(12))
                    report.AppendLine("  " + message.severity + " " + message.file + ":" + message.line + " " + message.message);
            }

            return report.ToString().TrimEnd();
        }
    }
}
