using System;
using System.Collections.Generic;
using System.Linq;
using nadena.dev.modular_avatar.core;
using UnityEngine;
using VRC.Dynamics;
using VRC.SDK3.Dynamics.Contact.Components;
using Wirenook.AdventureTools.Editor;
using Wirenook.Assets;
using Wirenook.Assets.Editor;
using Wirenook.SelectiveAnimation.Core;
using Wirenook.SelectiveAnimation.Editor;

namespace Wirenook.Meta.Crypt.Editor
{
    /// <summary>
    /// One piece of the crypt: a thing, or a few, that the game master
    /// sets down for the module. The crypt's tool calls each piece's steps
    /// in turn, as a kit calls its tools'.
    /// </summary>
    public interface ICryptPiece
    {
        void Things(StagePlan plan);
        void Build(CryptSet crypt);
        void Layers(CryptSet crypt);

        /// <param name="folder">The crypt's folder in the kit's menu.</param>
        void Menu(CryptSet crypt, GameObject folder);
    }

    /// <summary>
    /// What the crypt's pieces share while they are built: the kit they are
    /// part of, and two meshes of their own.
    ///
    /// The crypt does not add its shapes to the kit's meshes. Its things
    /// are laid out behind the scenes before anyone else is shown them, and
    /// the people backstage see them as spectres until then. That look is a
    /// property of a material, so the things that take it have to be drawn
    /// by a renderer that nothing else is drawn by.
    /// </summary>
    public sealed class CryptSet
    {
        /// <summary>The object the crypt's solid shapes are drawn by, directly under the kit's root.</summary>
        public const string SolidName = "Crypt Mesh";

        /// <summary>The object its PC-only shapes are drawn by: the ones that need a shader of this package's or the kit's own.</summary>
        public const string EffectsName = "Crypt Effects";

        public GameMaster Kit { get; }

        /// <summary>Solid shapes in the wirenook palette, one material.</summary>
        public ShapeMesh Solid { get; }

        /// <summary>
        /// PC-only shapes. Ask <see cref="Effect"/> for a slot first. A
        /// colour here is not a swatch: "sky" marks the far side of the
        /// rift, and a number from 0 to 1 is how light a thing on the far
        /// side is (Shaders/WirenookRift).
        /// </summary>
        public ShapeMesh Effects { get; }

        private readonly List<Material> _effects = new List<Material>();

        public CryptSet(GameMaster kit)
        {
            Kit = kit;
            Solid = new ShapeMesh(WirenookPalette.Uv);
            Effects = new ShapeMesh(tone => tone == "sky" ? new Vector2(0f, 1f)
                : string.IsNullOrEmpty(tone) ? Vector2.zero
                : new Vector2(float.Parse(tone, System.Globalization.CultureInfo.InvariantCulture), 0f)).Colour("");
        }

        internal IReadOnlyList<Material> EffectMaterials => _effects;

        public Stage Stage => Kit.Stage;
        public ControllerBuilder Fx => Kit.Fx;

        /// <summary>Prefix for the crypt's own parameters.</summary>
        public string Prefix => Kit.Prefix + "/Crypt";

        /// <summary>The slot of the PC-only mesh that is drawn with a material, added if it is not there.</summary>
        public int Effect(Material material)
        {
            if (material == null) throw new ArgumentNullException(nameof(material));
            var slot = _effects.IndexOf(material);
            if (slot >= 0) return slot;
            _effects.Add(material);
            return _effects.Count - 1;
        }

        public string Path(Transform target) => Kit.Path(target);

        /// <summary>
        /// A bone under a thing's own that a dial turns about the
        /// vertical. The stage stands things upright in the world's axes
        /// and syncs no heading, so a thing with a front is given one by
        /// its value: see <see cref="TurnLayer"/>.
        /// </summary>
        public Transform Turn(Transform bone) => GameMasterBuild.Bone(bone.gameObject, "Turn", Vector3.zero);

        /// <summary>Adds the layer that turns a thing to the heading its value says: a whole turn over the dial's travel.</summary>
        public void TurnLayer(string name, Transform turn, StageThing thing)
        {
            var path = Path(turn);
            var clip = Fx.Clip(name.ToLowerInvariant() + " turn", built =>
                built.Curve(path, typeof(Transform), "localEulerAnglesRaw.y", AnimationCurve.Linear(0f, 0f, 1f, 360f)));
            Fx.Layer(name + " Turn").State("Turn", clip).MotionTime(thing.Value);
        }

        /// <summary>
        /// An object for a thing's contacts, which rests switched off. A
        /// thing that is still being rehearsed is seen by the people
        /// backstage and must not act on them, so its contacts are on
        /// only where the thing is real: see <see cref="ContactsLayer"/>.
        /// </summary>
        public GameObject Contacts(Transform parent, Vector3 at, string name = "Contacts")
        {
            var holder = GameMasterBuild.Bone(parent.gameObject, name, at).gameObject;
            holder.SetActive(false);
            return holder;
        }

        /// <summary>Adds the layer that switches a thing's contacts on for an audience, <see cref="StageThing.Real"/> unless told otherwise.</summary>
        public void ContactsLayer(string name, GameObject contacts, StageThing thing, Audience when = null)
        {
            var path = Path(contacts.transform);
            AnimationClip Switched(bool on) => Fx.Clip(name.ToLowerInvariant() + " contacts " + (on ? "on" : "off"), clip => clip.Active(path, on));
            (when ?? thing.Real).Layer(Fx, name + " Contacts", Switched(true), Switched(false));
        }

        /// <summary>A sender of traits, as big as its object's scale makes it.</summary>
        public static VRCContactSender Sender(GameObject holder, float radius, params string[] tags)
        {
            var sender = FeaturePrefab.Ensure<VRCContactSender>(holder);
            sender.shapeType = ContactBase.ShapeType.Sphere;
            sender.radius = radius;
            sender.localOnly = false;
            sender.collisionTags = tags.ToList();
            sender.enabled = true;
            return sender;
        }

        /// <summary>A folder of the crypt's menu for one piece, with the entries every thing has: aim it, and whether it is on show.</summary>
        public GameObject MenuThing(GameObject parent, StageThing thing, string label, string icon)
        {
            var folder = FeaturePrefab.Child(parent, "Menu " + label);
            FeaturePrefab.MenuFolder(folder, label, icon);
            Stage.MenuAim(FeaturePrefab.Child(folder, "Menu Aim"), thing, "Aim");
            Stage.MenuShown(FeaturePrefab.Child(folder, "Menu Shown"), thing, "Set out");
            return folder;
        }
    }

    /// <summary>
    /// The crypt, as one tool of a game master's kit: the pieces a module
    /// called The Sunken Crypt needs, on top of everything the plain kit
    /// has. It is here to show what a kit can be made into for one
    /// adventure, with nothing but the kit's public parts
    /// (<see cref="IStageTool"/>), the skill checks of net.wirenook.contacts
    /// and VRChat's standard contact tags.
    ///
    ///   Hot, cold and windy zones   give off the trait they look like
    ///   A danger zone               shows where it will strike, then does
    ///   A barricade                 comes apart under hands, or fire
    ///   A chest with a padlock      opens to a hand once the key is found
    ///   A pendulum                  swings a blade
    ///   A rift                      a window on somewhere else, that hands seal
    ///
    /// All of them are rehearsed: the game master sets the course out
    /// with only the people backstage seeing it, as spectres, and one
    /// switch makes it live for everyone. Until then nothing in it can be
    /// touched.
    /// </summary>
    public sealed class CryptTool : IStageTool
    {
        public readonly List<ICryptPiece> Pieces;

        private CryptSet _crypt;

        public CryptTool(IEnumerable<ICryptPiece> pieces = null)
        {
            Pieces = (pieces ?? All()).ToList();
        }

        /// <summary>Every piece, in menu order.</summary>
        public static IEnumerable<ICryptPiece> All() => new ICryptPiece[]
        {
            new ElementPiece(), new DangerPiece(), new BarricadePiece(), new ChestPiece(), new PendulumPiece(), new RiftPiece(),
        };

        public void Things(StagePlan plan)
        {
            foreach (var piece in Pieces) piece.Things(plan);
        }

        public void Build(GameMaster kit)
        {
            _crypt = new CryptSet(kit);
            foreach (var piece in Pieces) piece.Build(_crypt);

            var solid = _crypt.Solid.Build(kit.Root, CryptSet.SolidName, CryptBuild.SolidMesh, GameMasterBuild.Material(CryptBuild.CryptMaterial));
            kit.Stage.Reach(solid);
            // Not part of the wearer's figure: a game master who goes unseen leaves the course standing.
            FeaturePrefab.Ensure<WirenookApart>(solid.gameObject);

            var effects = _crypt.Effects.Build(kit.Root, CryptSet.EffectsName, CryptBuild.EffectsMesh, _crypt.EffectMaterials.ToArray());
            kit.Stage.Reach(effects);
            FeaturePrefab.Ensure<WirenookApart>(effects.gameObject);
            FeaturePrefab.Ensure<WirenookPcOnly>(effects.gameObject);
        }

        public void Layers(GameMaster kit)
        {
            // Behind the scenes, the course is drawn as spectres.
            var fx = kit.Fx;
            AnimationClip Drawn(bool spectral) => fx.Clip(spectral ? "crypt spectral" : "crypt solid", clip =>
                clip.Material<SkinnedMeshRenderer>(CryptSet.SolidName, "_WirenookSpectral", spectral ? 1f : 0f));
            Audience.WhenFalse(kit.Stage.Live).Layer(fx, "Crypt Rehearsal", Drawn(true), Drawn(false));

            foreach (var piece in Pieces) piece.Layers(_crypt);
        }

        public void Menu(GameMaster kit)
        {
            var folder = kit.Folder("Crypt", "game-master");
            kit.Stage.MenuLive(FeaturePrefab.Child(folder, "Menu Live"), "Course is live");
            kit.Stage.MenuSet(FeaturePrefab.Child(folder, "Menu Set"));
            foreach (var piece in Pieces) piece.Menu(_crypt, folder);
        }
    }
}
