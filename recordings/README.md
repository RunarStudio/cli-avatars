# Grabaciones de CLI Avatars

Dos vídeos de la aplicación tal como está en `dev`, grabados con la app real sobre datos inventados.

| Archivo | Qué es |
|---|---|
| `demo.mp4` / `demo.png` | Demo corta: el escaparate de la herramienta, con música y los sonidos de la app. |
| `tutorial.mp4` / `tutorial.png` | Tutorial: cómo se usa y para qué sirve cada parte, con locución en español. |
| `SCRIPT.md` | El guion de los dos vídeos: tomas, planos, subtítulos y locución. |
| `tools/` | Los scripts que graban, ponen la voz y montan los vídeos. |

Commit de `dev` grabado: **a7519f9** («CHAT: New chat card, first-run tour and a plain To: line»), versión 0.4.0.

## Qué muestra cada vídeo

**Demo** (cartela, siete tomas, cierre): el mapa de la mazmorra con sus salas y el orquestador en la sala del trono;
avatares que trabajan, piensan o descansan; un agente que pide una decisión (burbuja, insignia, «Needs you», campana)
y la respuesta en un clic; el tablero de tareas con una tarjeta arrastrada a «done»; el chat de una tarea con Claude;
la vista del móvil a 400 px; y la barra de Update.

**Tutorial** (catorce capítulos, cada uno con su placa): arranque y tarjeta de inicio (se elige la carpeta que falta);
recorrido de bienvenida; el mapa (rueda, doble clic, minimapa); estados de los avatares; tu avatar; «Needs you»; temas
y sesiones (abrir una sala nueva); New chat; el tablero; chats de tarea con Claude y con Grok; cambiar el aspecto de un
avatar; la vista del móvil; Settings; y la comprobación de inicio y Update.

## Cómo se grabó

- La app real (`cli_avatars`), sin cambiar su código, en un Xvfb privado de 1920×1080. Nadie ve ni oye nada.
- Sin red: cada toma corre en un espacio de red nuevo que solo tiene loopback (`tools/netns.sh`, con `sudo unshare -n`).
- Datos inventados (`tools/seed.py`): cuatro salas, cuatro agentes, nueve tareas y sus chats. Una carpeta de datos
  propia por toma (`CLI_AVATARS_DATA_DIR`) y un HOME falso; nunca la carpeta de datos real.
- `claude` y `grok` son dos stubs que devuelven una respuesta escrita de antemano: ninguna llamada real a una IA.
- El ratón y el teclado son entrada X real (`xdotool`); la pantalla se captura con `ffmpeg x11grab`. La vista del móvil
  es la página de la app servida en loopback y abierta en Chrome headless y silenciado a 400 px.
- Solo para la grabación: las pantallas muestran «you» donde la app pone el nombre de su dueño; el selector de aspecto
  enseña solo las skins genéricas del kit (`ember_mage`, `forest_scout`, `frost_wanderer`); las pestañas Phone y Bots de
  Settings no salen en pantalla porque muestran un enlace con token y una URL.

## Sonido

- Música: compuesta por código (`tools/sound.py`), sin audio descargado.
- Efectos: los sonidos propios de la app (`cli_avatars/app/cues.py`) en el momento exacto en que la app los pidió, más
  clics, teclado y transiciones hechos por código.
- Locución del tutorial: Kokoro local, voz `em_alex`, sin red (`tools/voice.py`). Los subtítulos dicen lo mismo que la voz.

## Cómo volver a grabar

Hace falta Linux con Xvfb, xdotool, ffmpeg, `sudo -n` para `unshare -n`, Node con Playwright y Chrome, y Python con
Pillow y numpy (y Kokoro para la voz). Todas las rutas de salida deben ser absolutas.

```sh
python recordings/tools/script.py                      # regenera SCRIPT.md desde tools/script.py
python recordings/tools/voice.py "$VOZ"                # locución: un WAV por frase y durations.json
recordings/tools/record.sh demo "$TOMAS/demo"          # una toma por carpeta: raw.mkv, marks.jsonl, cues.jsonl
REC_VO="$VOZ/durations.json" recordings/tools/record.sh tutorial "$TOMAS/tutorial"
python recordings/tools/edit.py demo "$TOMAS/demo" recordings/demo.mp4
python recordings/tools/edit.py tutorial "$TOMAS/tutorial" recordings/tutorial.mp4 --vo "$VOZ" --size 1280x720
```

`record.sh` acepta nombres de toma para repetir solo esas (por ejemplo `record.sh demo "$TOMAS/demo" d_board`).
`edit.py` escribe el MP4 (H.264 + AAC, por debajo de 24 MB) y su póster PNG al lado.
