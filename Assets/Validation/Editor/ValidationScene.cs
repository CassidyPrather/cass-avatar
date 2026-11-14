using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Wirenook.Validation.Editor
{
    /// <summary>
    /// Generates Assets/Scenes/Validation.unity: a stage with a set of fixed
    /// cameras and lighting conditions for judging model work. Open it to look
    /// around by hand, or let <see cref="ContactSheets"/> photograph an avatar
    /// from every camera under every condition.
    /// </summary>
    public static class ValidationScene
    {
        public const string ScenePath = "Assets/Scenes/Validation.unity";
        public const string CamerasRoot = "Cameras";
        public const string LightingRoot = "Lighting";
        public const string AvatarSlot = "Avatar Slot";

        /// <summary>The height cameras are framed for; avatars near it fit every shot.</summary>
        private const float Height = 1.8f;

        private readonly struct Shot
        {
            public readonly string Name;
            public readonly float TargetHeight;
            public readonly float Yaw;
            public readonly float Pitch;
            public readonly float Distance;
            public readonly float FieldOfView;

            public Shot(string name, float targetHeight, float yaw, float pitch, float distance, float fieldOfView = 24f)
            {
                Name = name;
                TargetHeight = targetHeight;
                Yaw = yaw;
                Pitch = pitch;
                Distance = distance;
                FieldOfView = fieldOfView;
            }
        }

        // Yaw 0 looks at the avatar's front; positive yaw walks the camera
        // round toward +X. Heights are fractions of Height.
        private static readonly Shot[] Shots =
        {
            new Shot("Front", 0.5f, 0f, 0f, 5.0f),
            new Shot("Three-Quarter", 0.5f, 35f, 6f, 5.0f),
            new Shot("Left", 0.5f, 90f, 0f, 5.0f),
            new Shot("Three-Quarter Back", 0.5f, 145f, 6f, 5.0f),
            new Shot("Back", 0.5f, 180f, 0f, 5.0f),
            new Shot("Right", 0.5f, -90f, 0f, 5.0f),
            new Shot("High", 0.5f, 25f, 50f, 5.2f),
            new Shot("Low", 0.5f, 25f, -35f, 5.2f),
            new Shot("Upper Body", 0.76f, 15f, 4f, 2.6f),
            new Shot("Lower Body", 0.27f, 15f, 4f, 2.8f),
            new Shot("Feet", 0.06f, 30f, 25f, 1.5f),
            new Shot("Face", 0.9f, 0f, 0f, 1.25f, 20f),
            new Shot("Face Three-Quarter", 0.9f, 40f, 4f, 1.25f, 20f),
            new Shot("Face Profile", 0.9f, 90f, 0f, 1.25f, 20f),
            new Shot("Face From Below", 0.9f, 15f, -40f, 1.25f, 20f),
            // As close as a friend leaning in: checks near-plane clipping.
            new Shot("Nose To Nose", 0.9f, 8f, 0f, 0.22f, 60f),
        };

        [MenuItem("Tools/Wirenook/Validation/Rebuild Scene")]
        public static void Rebuild()
        {
            Directory.CreateDirectory(Path.GetDirectoryName(ScenePath));
            var scene = SceneManager.GetSceneByPath(ScenePath);
            if (scene.isLoaded)
            {
                // Already open: empty it and build again in place.
                foreach (var root in scene.GetRootGameObjects()) Object.DestroyImmediate(root);
            }
            else
            {
                scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, CanAddScene() ? NewSceneMode.Additive : NewSceneMode.Single);
            }

            var previous = SceneManager.GetActiveScene();
            var wasAdded = scene != previous;
            // Ambient light is saved with the active scene, so this one has to
            // be active while its lighting is set up.
            SceneManager.SetActiveScene(scene);
            BuildStage(scene);
            BuildCameras(scene);
            BuildLighting(scene);
            Move(new GameObject(AvatarSlot), scene);
            EditorSceneManager.SaveScene(scene, ScenePath);
            if (wasAdded)
            {
                SceneManager.SetActiveScene(previous);
                EditorSceneManager.CloseScene(scene, true);
            }

            Debug.Log("[validation] Rebuilt " + ScenePath);
        }

        /// <summary>
        /// Opens the validation scene, beside whatever is open when that is
        /// possible. Unity will not add a scene next to an untitled one, so an
        /// untitled scene with nothing unsaved in it is replaced instead.
        /// </summary>
        /// <param name="added">True when the caller should close the scene again.</param>
        public static Scene Open(out bool added)
        {
            var scene = SceneManager.GetSceneByPath(ScenePath);
            added = false;
            if (scene.isLoaded) return scene;
            added = CanAddScene();
            return EditorSceneManager.OpenScene(ScenePath, added ? OpenSceneMode.Additive : OpenSceneMode.Single);
        }

        private static bool CanAddScene()
        {
            var active = SceneManager.GetActiveScene();
            if (!string.IsNullOrEmpty(active.path)) return true;
            if (active.isDirty)
            {
                throw new System.InvalidOperationException(
                    "The open scene is untitled and has unsaved changes. Save it or discard it, then try again.");
            }

            return false;
        }

        private static void Move(GameObject gameObject, Scene scene)
        {
            SceneManager.MoveGameObjectToScene(gameObject, scene);
        }

        private static void BuildStage(Scene scene)
        {
            var stage = new GameObject("Stage");
            Move(stage, scene);

            // A mid-grey floor and backdrop: neutral enough to judge colour
            // against, and they catch the avatar's shadow so floating feet show.
            const string materialPath = "Assets/Validation/Generated/Stage Grey.mat";
            var material = AssetDatabase.LoadAssetAtPath<Material>(materialPath);
            if (material == null)
            {
                Directory.CreateDirectory(Path.GetDirectoryName(materialPath));
                material = new Material(Shader.Find("Standard"));
                AssetDatabase.CreateAsset(material, materialPath);
            }

            material.color = new Color(0.42f, 0.42f, 0.45f);
            material.SetFloat("_Glossiness", 0f);
            EditorUtility.SetDirty(material);

            var floor = GameObject.CreatePrimitive(PrimitiveType.Plane);
            floor.name = "Floor";
            floor.transform.SetParent(stage.transform, false);
            floor.transform.localScale = new Vector3(3f, 1f, 3f);
            floor.GetComponent<Renderer>().sharedMaterial = material;
            Object.DestroyImmediate(floor.GetComponent<Collider>());
        }

        private static void BuildCameras(Scene scene)
        {
            var root = new GameObject(CamerasRoot);
            Move(root, scene);
            foreach (var shot in Shots)
            {
                var cameraObject = new GameObject(shot.Name);
                cameraObject.transform.SetParent(root.transform, false);
                var camera = cameraObject.AddComponent<Camera>();
                camera.fieldOfView = shot.FieldOfView;
                camera.nearClipPlane = 0.01f;
                camera.farClipPlane = 100f;
                camera.clearFlags = CameraClearFlags.SolidColor;
                camera.backgroundColor = new Color(0.30f, 0.31f, 0.35f);
                // Scene cameras would all fight for the Game view; the tools
                // render them one at a time instead.
                camera.enabled = false;

                var target = new Vector3(0f, shot.TargetHeight * Height, 0f);
                // The avatar faces +Z, so its front is seen from +Z.
                var offset = Quaternion.Euler(-shot.Pitch, shot.Yaw, 0f) * Vector3.forward * shot.Distance;
                cameraObject.transform.position = target + offset;
                cameraObject.transform.LookAt(target);
            }
        }

        private static void BuildLighting(Scene scene)
        {
            var root = new GameObject(LightingRoot);
            Move(root, scene);

            var neutral = Condition(root, "Neutral", new Color(0.35f, 0.35f, 0.38f),
                "The reference look: colours, shading bands, overall read.");
            Directional(neutral, new Vector3(35f, 200f, 0f), Color.white, 1f);

            Condition(root, "Dark", Color.black,
                "No light at all. The avatar should go black: any part still visible has a brightness floor or unlit emission.");

            var dim = Condition(root, "Dim", new Color(0.03f, 0.03f, 0.05f),
                "A dark club. The avatar should be dim but readable, never glowing against the room.");
            Directional(dim, new Vector3(50f, 160f, 0f), new Color(0.6f, 0.65f, 1f), 0.12f);

            var harsh = Condition(root, "Harsh Side", Color.black,
                "One hard light from the side with nothing filling the shadows: shows where the shade boundary falls and whether normals are sane.");
            Directional(harsh, new Vector3(10f, 270f, 0f), Color.white, 1.4f);

            var overbright = Condition(root, "Overbright", new Color(1.2f, 1.2f, 1.2f),
                "A badly lit world several times too bright. The avatar should not blow out to white.");
            Directional(overbright, new Vector3(60f, 180f, 0f), Color.white, 3.5f);

            var coloured = Condition(root, "Coloured", new Color(0.05f, 0.02f, 0.08f),
                "Saturated point lights from both sides: checks point-light response and that colours tint rather than replace.");
            Point(coloured, new Vector3(1.6f, 1.4f, 1.2f), new Color(1f, 0f, 0.9f), 2.2f);
            Point(coloured, new Vector3(-1.6f, 1.0f, 1.0f), new Color(0.45f, 0.96f, 1f), 2.2f);

            var backlit = Condition(root, "Backlit", new Color(0.08f, 0.08f, 0.1f),
                "Light from behind: the front should fall into shade without the silhouette breaking up.");
            Directional(backlit, new Vector3(25f, 10f, 0f), new Color(1f, 0.95f, 0.85f), 1.3f);

            neutral.Activate();
        }

        private static LightingCondition Condition(GameObject root, string name, Color ambient, string looksFor)
        {
            var conditionObject = new GameObject(name);
            conditionObject.transform.SetParent(root.transform, false);
            var condition = conditionObject.AddComponent<LightingCondition>();
            condition.ambient = ambient;
            condition.looksFor = looksFor;
            return condition;
        }

        private static void Directional(LightingCondition condition, Vector3 euler, Color colour, float intensity)
        {
            var lightObject = new GameObject("Directional");
            lightObject.transform.SetParent(condition.transform, false);
            lightObject.transform.rotation = Quaternion.Euler(euler);
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.color = colour;
            light.intensity = intensity;
            light.shadows = LightShadows.Soft;
        }

        private static void Point(LightingCondition condition, Vector3 position, Color colour, float intensity)
        {
            var lightObject = new GameObject("Point");
            lightObject.transform.SetParent(condition.transform, false);
            lightObject.transform.position = position;
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = colour;
            light.intensity = intensity;
            light.range = 6f;
        }

        public static IEnumerable<Camera> Cameras(Scene scene)
        {
            return Root(scene, CamerasRoot).GetComponentsInChildren<Camera>(true);
        }

        public static IEnumerable<LightingCondition> Conditions(Scene scene)
        {
            return Root(scene, LightingRoot).GetComponentsInChildren<LightingCondition>(true);
        }

        public static GameObject Root(Scene scene, string name)
        {
            var root = scene.GetRootGameObjects().FirstOrDefault(candidate => candidate.name == name);
            if (root == null) throw new FileNotFoundException("The validation scene has no \"" + name + "\"; rebuild it.", ScenePath);
            return root;
        }
    }
}
