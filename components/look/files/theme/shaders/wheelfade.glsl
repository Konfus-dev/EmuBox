// The system wheel's fade: a row is fully there near the middle of the wheel and fades out as it
// turns towards the top or bottom. Measured as the angle of each pixel around the orb's middle
// (0.27 across, 0.485 down), so a whole row (a spoke of the wheel) fades evenly.
#if defined(VERTEX)
#if __VERSION__ >= 130
#define COMPAT_VARYING out
#define COMPAT_ATTRIBUTE in
#else
#define COMPAT_VARYING varying
#define COMPAT_ATTRIBUTE attribute
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
uniform   vec2 Resolution;
void main(void)
{
	vec4 t = COMPAT_TEXTURE(u_tex, v_tex);
	vec2 screen = Resolution.x > 0.0 ? Resolution : vec2(1920.0, 1080.0);
	vec2 orb = vec2(0.27, 1.0 - 0.485) * screen;          // gl_FragCoord counts up from the bottom
	vec2 d = gl_FragCoord.xy - orb;
	float angle = degrees(atan(abs(d.y), max(d.x, 1.0)));
	float keep = 1.0 - smoothstep(10.0, 34.0, angle);
	FragColor = vec4(t.rgb * v_col.rgb, t.a * v_col.a * keep);
}
#endif
