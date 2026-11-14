// Hologram look for console logos: any logo becomes a pale, slightly scan-lined projection.
#if defined(VERTEX)
#if __VERSION__ >= 130
#define COMPAT_VARYING out
#define COMPAT_ATTRIBUTE in
#else
#define COMPAT_VARYING varying
#define COMPAT_ATTRIBUTE attribute
#endif
#ifdef GL_ES
#define COMPAT_PRECISION mediump
#else
#define COMPAT_PRECISION
#endif
uniform   mat4 MVPMatrix;
COMPAT_ATTRIBUTE vec2 VertexCoord;
COMPAT_ATTRIBUTE vec2 TexCoord;
COMPAT_ATTRIBUTE vec4 COLOR;
COMPAT_VARYING   vec2 v_tex;
COMPAT_VARYING   vec4 v_col;
void main(void)
{
	gl_Position = MVPMatrix * vec4(VertexCoord.xy, 0.0, 1.0);
	v_tex       = TexCoord;
	v_col       = COLOR;
}
#elif defined(FRAGMENT)
#if __VERSION__ >= 130
#define COMPAT_VARYING in
#define COMPAT_TEXTURE texture
out vec4 FragColor;
#else
#define COMPAT_VARYING varying
#define FragColor gl_FragColor
#define COMPAT_TEXTURE texture2D
#endif
#ifdef GL_ES
#ifdef GL_FRAGMENT_PRECISION_HIGH
precision highp float;
#else
precision mediump float;
#endif
#endif
COMPAT_VARYING   vec4      v_col;
COMPAT_VARYING   vec2      v_tex;
uniform   sampler2D u_tex;
void main(void)
{
	vec4 t = COMPAT_TEXTURE(u_tex, v_tex);
	float lum = dot(t.rgb, vec3(0.299, 0.587, 0.114));
	// dark parts of the logo become green light, bright parts become pale green-white light
	vec3 holo = mix(vec3(0.30, 1.0, 0.48), vec3(0.86, 1.0, 0.88), smoothstep(0.15, 0.9, lum));
	// scan lines: one dim line in every three, plus a slower, softer banding
	float line = 0.58 + 0.42 * step(1.0, mod(gl_FragCoord.y, 3.0));
	float band = 0.90 + 0.10 * sin(gl_FragCoord.y * 0.16);
	float a = t.a * v_col.a * (0.78 + 0.22 * lum) * line * band;
	FragColor = vec4(holo * v_col.rgb, a);
}
#endif
