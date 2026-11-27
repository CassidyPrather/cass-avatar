// A window on somewhere else. Three materials of this one shader, drawn in
// this order by their render queues, make a rift:
//
//   the window   the body of the tear: a closed shape with two faces and an
//                edge. Draws no colour: it marks its pixels in one bit of the
//                stencil buffer and writes its own depth over whatever was
//                behind it.
//   the beyond   everything on the far side. Drawn only on marked pixels,
//                and only where it lies behind the window's surface (the
//                depth the window wrote), so that what is between the
//                viewer and the window is not mistaken for what is through
//                it. It does not write depth, and is drawn in the order its
//                triangles come in: farthest first.
//   the rim      the body again, from the same points, to take the mark off.
//                Its first UV coordinate is how much light a face has: the
//                faces are cut into bands, and the bands along the torn edge
//                are lit, in steps and not a gradient.
//
// The far side is shaded here and not by a texture. A vertex whose second
// UV coordinate is above a half belongs to the sky: its colour comes from
// the direction it is seen in, which is what makes a sky look far away,
// since it does not slide as the viewer moves. Anything else is a flat
// shade between _Deep and _Glow, by its first UV coordinate, and does
// slide, because it really is where it is drawn.
//
// _Heading is which way the tear faces, as a share of a turn about the
// vertical; the build animates it with the tear's own heading. The sky is
// looked up in the tear's frame, so the eye stays behind the same face.
Shader "Wirenook/Rift"
{
    Properties
    {
        [Enum(Window,0,Beyond,1,Rim,2)] _Part ("Which part this material is", Float) = 0
        _Deep ("The dark of the far side", Color) = (0.03, 0.01, 0.07, 1)
        _Glow ("Its light", Color) = (0.42, 0.2, 0.75, 1)
        _Eye ("The eye in its sky", Color) = (0.75, 1, 0.55, 1)
        _EyeDirection ("Where the eye is (a direction in the tear's frame)", Vector) = (0.07, 0.1, -1, 0)
        _Heading ("Which way the tear faces (a share of a turn)", Range(0, 1)) = 0
        _Bit ("Stencil bit it marks (a power of two)", Float) = 8
        [Enum(UnityEngine.Rendering.CompareFunction)] _ZTest ("Depth test", Float) = 4
        [Enum(Off,0,On,1)] _ZWrite ("Depth write", Float) = 0
        [Enum(UnityEngine.Rendering.CullMode)] _Cull ("Cull", Float) = 2
        _ColorMask ("Colour channels written (0 or 15)", Float) = 15
        [Enum(UnityEngine.Rendering.CompareFunction)] _StencilComp ("Stencil test", Float) = 8
        [Enum(UnityEngine.Rendering.StencilOp)] _StencilPass ("Stencil when drawn", Float) = 0
    }

    SubShader
    {
        Tags
        {
            // After everything solid and the sky, before the stage's volumes and most see-through things.
            "Queue" = "Transparent-120"
            "RenderType" = "Transparent"
            "IgnoreProjector" = "True"
            "DisableBatching" = "True"
            // With the avatar's shaders blocked there is no window: show nothing rather than a grey shape.
            "VRCFallback" = "Hidden"
        }

        Pass
        {
            Cull [_Cull]
            ZTest [_ZTest]
            ZWrite [_ZWrite]
            ColorMask [_ColorMask]
            Blend SrcAlpha OneMinusSrcAlpha
            Stencil
            {
                Ref [_Bit]
                ReadMask [_Bit]
                WriteMask [_Bit]
                Comp [_StencilComp]
                Pass [_StencilPass]
            }

            CGPROGRAM
            #pragma vertex vert
            #pragma fragment frag
            #pragma multi_compile_instancing
            #include "UnityCG.cginc"

            float _Part;
            float4 _Deep;
            float4 _Glow;
            float4 _Eye;
            float4 _EyeDirection;
            float _Heading;

            struct appdata
            {
                float4 vertex : POSITION;
                float3 normal : NORMAL;
                float2 uv : TEXCOORD0;
                UNITY_VERTEX_INPUT_INSTANCE_ID
            };

            struct v2f
            {
                float4 pos : SV_POSITION;
                float2 uv : TEXCOORD0;
                float3 world : TEXCOORD1;
                float3 normal : TEXCOORD2;
                UNITY_VERTEX_OUTPUT_STEREO
            };

            v2f vert(appdata v)
            {
                v2f o;
                UNITY_SETUP_INSTANCE_ID(v);
                UNITY_INITIALIZE_OUTPUT(v2f, o);
                UNITY_INITIALIZE_VERTEX_OUTPUT_STEREO(o);
                o.pos = UnityObjectToClipPos(v.vertex);
                o.uv = v.uv;
                o.world = mul(unity_ObjectToWorld, v.vertex).xyz;
                o.normal = UnityObjectToWorldNormal(v.normal);
                return o;
            }

            float hash(float3 p)
            {
                p = frac(p * 0.3183099 + 0.1);
                p *= 17.0;
                return frac(p.x * p.y * p.z * (p.x + p.y + p.z));
            }

            // A direction in the world, in the tear's frame: the turn about the vertical undone.
            float3 unturned(float3 dir)
            {
                float angle = _Heading * 6.283185307;
                float s = sin(angle);
                float c = cos(angle);
                return float3(dir.x * c - dir.z * s, dir.y, dir.x * s + dir.z * c);
            }

            // The sky of the far side, from the direction it is looked at in.
            float3 sky(float3 dir)
            {
                // Dark overhead and underfoot, a band of light at the horizon.
                float horizon = 1.0 - abs(dir.y);
                float3 colour = lerp(_Deep.rgb, _Glow.rgb, pow(horizon, 2.5) * 0.9);
                colour += _Glow.rgb * 0.5 * pow(horizon, 12.0);

                // A few faint stars that do not twinkle fast enough to bother anyone.
                float3 cell = floor(dir * 110.0);
                float star = step(0.9965, hash(cell)) * step(0.05, dir.y);
                colour += star * 0.5 * (0.6 + 0.4 * sin(_Time.y * 0.8 + hash(cell + 3.0) * 6.283));

                // The eye: a pale disc with a slit in it, and a halo.
                float3 eye = normalize(_EyeDirection.xyz);
                float3 right = normalize(cross(float3(0, 1, 0), eye));
                float3 up = cross(eye, right);
                float facing = dot(dir, eye);
                float2 at = float2(dot(dir, right), dot(dir, up));
                float breathe = 0.9 + 0.1 * sin(_Time.y * 0.6);
                const float size = 0.16;
                float inside = step(0.0, facing) * (1.0 - smoothstep(size - 0.012, size, length(at)));
                float halo = step(0.0, facing) * (1.0 - smoothstep(size, size * 2.6, length(at)));
                colour += _Eye.rgb * halo * halo * 0.22 * breathe;
                float limb = 1.0 - 0.45 * saturate(length(at) / size);
                float slit = 1.0 - smoothstep(0.0, 0.012, abs(at.x) - 0.028 * (1.0 - saturate(abs(at.y) / (size * 0.82))));
                slit *= step(abs(at.y), size * 0.82);
                colour = lerp(colour, _Eye.rgb * limb * breathe, inside);
                colour = lerp(colour, _Deep.rgb * 0.4, inside * slit);

                // Land under it: a broken line of peaks all the way round, black against the light.
                float turn = atan2(dir.z, dir.x) * 0.15915494;
                float peaks = -0.02 + 0.09 * abs(frac(turn * 9.0) - 0.5) + 0.05 * abs(frac(turn * 23.0 + 0.3) - 0.5)
                    + 0.04 * abs(frac(turn * 4.0 + 0.7) - 0.5);
                float land = 1.0 - smoothstep(peaks - 0.006, peaks, dir.y);
                // The ground runs off into a haze that the light catches.
                float3 ground = lerp(_Glow.rgb * 0.3, _Deep.rgb * 0.3, saturate((peaks - dir.y) * 3.5));
                colour = lerp(colour, ground, land);
                return colour;
            }

            fixed4 frag(v2f i) : SV_Target
            {
                float3 toEye = normalize(_WorldSpaceCameraPos - i.world);
                if (_Part < 0.5)
                {
                    // The window writes no colour (its colour mask is nought).
                    return 0;
                }

                if (_Part < 1.5)
                {
                    if (i.uv.y > 0.5) return fixed4(sky(unturned(-toEye)), 1);
                    return fixed4(lerp(_Deep.rgb * 0.35, _Glow.rgb, saturate(i.uv.x)), 1);
                }

                // The rim: the bands along the torn edge, and a little light where a face is seen edge on.
                float band = saturate(i.uv.x);
                float edge = 1.0 - abs(dot(normalize(i.normal), toEye));
                edge = edge * edge;
                float3 light = lerp(_Glow.rgb * 1.3, float3(1.0, 0.96, 1.0), band * 0.6);
                return fixed4(light, max(band, edge * edge * 0.6));
            }
            ENDCG
        }
    }
}
