// A file-based command bridge into a running editor, so scripts (and agents)
// can drive Unity without closing it for a batch-mode run.
//
// scripts/unity-bridge.py drops a request into Temp/UnityBridge/in/<id>.json
// and waits for Temp/UnityBridge/out/<id>.json. Requests run on the main
// thread from EditorApplication.update, which keeps ticking while the editor
// is in the background.
//
// This assembly references nothing else in the project on purpose: when some
// other assembly fails to compile, the bridge still loads and can report why.
using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Reflection;
using System.Text;
using System.Threading.Tasks;
using UnityEditor;
using UnityEditor.Compilation;
using UnityEngine;

namespace Wirenook.DevTools
{
    [InitializeOnLoad]
    public static class UnityBridge
    {
        private const string PendingRefreshKey = "Wirenook.UnityBridge.PendingRefresh";
        private const string CompileErrorsKey = "Wirenook.UnityBridge.CompileErrors";
        private const string LastBusyKey = "Wirenook.UnityBridge.LastBusy";
        private const double PollInterval = 0.2;

        /// <summary>
        /// How long the editor must stay idle before a refresh counts as done.
        /// Unity starts compiling a moment after the import that found changed
        /// scripts returns; answering in that gap would let the next request
        /// run against the assemblies that are about to be replaced.
        /// </summary>
        private const double SettleSeconds = 2.0;

        private static readonly string Root = Path.Combine(Directory.GetCurrentDirectory(), "Temp", "UnityBridge");
        private static readonly string InDir = Path.Combine(Root, "in");
        private static readonly string OutDir = Path.Combine(Root, "out");

        private static readonly List<LogEntry> Captured = new List<LogEntry>();
        private static readonly List<Running> RunningTasks = new List<Running>();
        private static bool _capturing;
        private static double _nextPoll;

        [Serializable]
        private class Request
        {
            public string command;
            public string method;
            public string[] args;
        }

        [Serializable]
        private class LogEntry
        {
            public string type;
            public string message;
        }

        [Serializable]
        private class Response
        {
            public bool ok;
            public string result;
            public string error;
            public List<LogEntry> logs = new List<LogEntry>();
        }

        private class Running
        {
            public string Id;
            public Task Task;
            public List<LogEntry> Logs;
        }

        static UnityBridge()
        {
            Directory.CreateDirectory(InDir);
            Directory.CreateDirectory(OutDir);
            File.WriteAllText(Path.Combine(Root, "alive"), DateTime.UtcNow.ToString("o"));

            Application.logMessageReceivedThreaded += OnLog;
            CompilationPipeline.compilationStarted += _ => SessionState.SetString(CompileErrorsKey, "");
            CompilationPipeline.assemblyCompilationFinished += OnAssemblyCompiled;
            EditorApplication.update += Update;
        }

        private static void OnLog(string condition, string stackTrace, LogType type)
        {
            if (!_capturing) return;
            lock (Captured)
            {
                if (Captured.Count >= 400) return;
                var message = condition;
                if (type == LogType.Exception || type == LogType.Error)
                {
                    message += "\n" + string.Join("\n", (stackTrace ?? "").Split('\n').Take(12));
                }
                Captured.Add(new LogEntry { type = type.ToString(), message = message });
            }
        }

        private static void OnAssemblyCompiled(string assembly, CompilerMessage[] messages)
        {
            var errors = messages.Where(m => m.type == CompilerMessageType.Error).Select(m => m.message).ToArray();
            if (errors.Length == 0) return;
            var existing = SessionState.GetString(CompileErrorsKey, "");
            SessionState.SetString(CompileErrorsKey, existing + string.Join("\n", errors) + "\n");
        }

        private static void Update()
        {
            if (EditorApplication.timeSinceStartup < _nextPoll) return;
            _nextPoll = EditorApplication.timeSinceStartup + PollInterval;

            FinishTasks();
            FinishRefresh();

            // Hold new work while a refresh is settling; a domain reload
            // mid-request would drop its response.
            if (EditorApplication.isCompiling || EditorApplication.isUpdating) return;
            if (!string.IsNullOrEmpty(SessionState.GetString(PendingRefreshKey, ""))) return;

            string[] files;
            try
            {
                files = Directory.GetFiles(InDir, "*.json");
            }
            catch (IOException)
            {
                return;
            }

            Array.Sort(files, StringComparer.Ordinal);
            foreach (var file in files)
            {
                var id = Path.GetFileNameWithoutExtension(file);
                string body;
                try
                {
                    body = File.ReadAllText(file);
                    File.Delete(file);
                }
                catch (IOException)
                {
                    continue; // still being written; pick it up next tick
                }

                Handle(id, body);
                if (!string.IsNullOrEmpty(SessionState.GetString(PendingRefreshKey, ""))) return;
            }
        }

        private static void Handle(string id, string body)
        {
            var response = new Response();
            BeginCapture();
            try
            {
                var request = JsonUtility.FromJson<Request>(body);
                switch (request.command)
                {
                    case "ping":
                        response.ok = true;
                        response.result = Application.unityVersion;
                        break;
                    case "refresh":
                        SessionState.SetString(PendingRefreshKey, id);
                        SessionState.SetString(CompileErrorsKey, "");
                        SessionState.SetFloat(LastBusyKey, (float)EditorApplication.timeSinceStartup);
                        AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
                        EndCapture(null);
                        return; // FinishRefresh answers once the editor settles
                    case "menu":
                        response.ok = EditorApplication.ExecuteMenuItem(request.method);
                        if (!response.ok) response.error = "no such menu item: " + request.method;
                        break;
                    case "invoke":
                        var value = Invoke(request.method, request.args ?? new string[0]);
                        if (value is Task task)
                        {
                            RunningTasks.Add(new Running { Id = id, Task = task, Logs = new List<LogEntry>() });
                            return; // capture stays on until the task ends
                        }
                        response.ok = true;
                        response.result = value?.ToString();
                        break;
                    default:
                        response.error = "unknown command: " + request.command;
                        break;
                }
            }
            catch (TargetInvocationException e)
            {
                response.error = (e.InnerException ?? e).ToString();
            }
            catch (Exception e)
            {
                response.error = e.ToString();
            }

            EndCapture(response.logs);
            Write(id, response);
        }

        private static object Invoke(string qualified, string[] args)
        {
            var split = qualified.LastIndexOf('.');
            if (split < 0) throw new ArgumentException("expected Namespace.Type.Method, got " + qualified);
            var typeName = qualified.Substring(0, split);
            var methodName = qualified.Substring(split + 1);

            var type = AppDomain.CurrentDomain.GetAssemblies()
                .Select(a => a.GetType(typeName, false))
                .FirstOrDefault(t => t != null);
            if (type == null) throw new ArgumentException("type not found: " + typeName);

            const BindingFlags flags = BindingFlags.Static | BindingFlags.Public | BindingFlags.NonPublic;
            foreach (var method in type.GetMethods(flags).Where(m => m.Name == methodName))
            {
                var parameters = method.GetParameters();
                if (parameters.Length == 0 && args.Length == 0) return method.Invoke(null, null);
                if (parameters.Length == 1 && parameters[0].ParameterType == typeof(string[]))
                    return method.Invoke(null, new object[] { args });
                if (parameters.Length == args.Length && parameters.All(p => p.ParameterType == typeof(string)))
                    return method.Invoke(null, args.Cast<object>().ToArray());
            }

            throw new ArgumentException(
                "no static " + qualified + " taking " + args.Length + " string argument(s), string[] or nothing");
        }

        private static void FinishTasks()
        {
            for (var i = RunningTasks.Count - 1; i >= 0; i--)
            {
                var running = RunningTasks[i];
                if (!running.Task.IsCompleted) continue;
                RunningTasks.RemoveAt(i);

                var response = new Response();
                if (running.Task.IsFaulted)
                {
                    response.error = running.Task.Exception?.GetBaseException().ToString();
                }
                else if (running.Task.IsCanceled)
                {
                    response.error = "cancelled";
                }
                else
                {
                    response.ok = true;
                    var resultProperty = running.Task.GetType().GetProperty("Result");
                    // Task<VoidTaskResult> is what a plain async Task reports; nothing to show.
                    if (resultProperty != null && running.Task.GetType().IsGenericType &&
                        resultProperty.PropertyType.Name != "VoidTaskResult")
                    {
                        response.result = resultProperty.GetValue(running.Task)?.ToString();
                    }
                }

                if (RunningTasks.Count == 0) EndCapture(response.logs);
                Write(running.Id, response);
            }
        }

        private static void FinishRefresh()
        {
            var id = SessionState.GetString(PendingRefreshKey, "");
            if (string.IsNullOrEmpty(id)) return;
            if (EditorApplication.isCompiling || EditorApplication.isUpdating)
            {
                SessionState.SetFloat(LastBusyKey, (float)EditorApplication.timeSinceStartup);
                return;
            }

            if (EditorApplication.timeSinceStartup - SessionState.GetFloat(LastBusyKey, 0f) < SettleSeconds) return;

            SessionState.SetString(PendingRefreshKey, "");
            var errors = SessionState.GetString(CompileErrorsKey, "").Trim();
            var response = new Response
            {
                ok = errors.Length == 0 && !EditorUtility.scriptCompilationFailed,
                result = errors.Length == 0 ? "refreshed" : null,
                error = errors.Length == 0
                    ? (EditorUtility.scriptCompilationFailed ? "script compilation failed (see Editor.log)" : null)
                    : errors,
            };
            Write(id, response);
        }

        private static void BeginCapture()
        {
            lock (Captured) Captured.Clear();
            _capturing = true;
        }

        private static void EndCapture(List<LogEntry> into)
        {
            _capturing = false;
            lock (Captured)
            {
                into?.AddRange(Captured);
                Captured.Clear();
            }
        }

        private static void Write(string id, Response response)
        {
            Directory.CreateDirectory(OutDir);
            var temp = Path.Combine(OutDir, id + ".tmp");
            File.WriteAllText(temp, JsonUtility.ToJson(response), new UTF8Encoding(false));
            var final = Path.Combine(OutDir, id + ".json");
            if (File.Exists(final)) File.Delete(final);
            File.Move(temp, final);
        }
    }
}
