# Kit de mazmorra: 67 sprites

Rejilla isométrica 2:1. Una casilla mide 32x16 px; una unidad de altura, 16 px. Fondo transparente.
Ancla = píxel del sprite que cae sobre el vértice superior (norte) de su casilla (u,v) a la altura z:
`x = X0 + (u - v) * 16 - anclaX`, `y = Y0 + (u + v) * 8 - z * 16 - anclaY`.
Orden de pintado: roca, losas, muros, luz, manchas, objetos de atrás (u+v menor) hacia delante, antorchas, rejas.
Huella "muro": se coloca en la casilla de un muro der. (grilletes, antorcha der.) o izq. (antorcha izq.).
Huella "luz": ancla en su centro, mezcla aditiva; la luz de sala va en el centro de la sala, el halo sobre la llama.
Estantería y estante de pociones miran a la derecha: van contra el muro izq.
`4x/` guarda cada sprite ampliado cuatro veces.
Placa (b31): campo de texto oscuro en (4,6), 32x5; la app escribe los recuentos encima. Va en un muro der. entre las antorchas.
Halos de estado (b32-b35): a los pies del nodo, como luz; verde busy, azul thinking, rojo error, ámbar blocked.
Insignia +n (b36): ancla en su centro; la cifra va en (6,2), copiada de `b37-cifras.png` (celdas 3x5, paso 4 px, 0-9).
Filas de avatar: `avatar-rows/error.png` y `avatar-rows/blocked.png`, 160x40 (4 cuadros de 40x40), ver README.md.

| archivo | nombre | grupo | tamaño px | huella | ancla x,y |
|---|---|---|---|---|---|
| b01-losa.png | losa | base | 33x24 | 1x1 | 16,0 |
| b02-losa-clara.png | losa clara | base | 33x24 | 1x1 | 16,0 |
| b03-losa-oscura.png | losa oscura | base | 33x24 | 1x1 | 16,0 |
| b04-losa-agrietada.png | losa agrietada | base | 33x24 | 1x1 | 16,0 |
| b05-losa-rejilla.png | losa con rejilla | base | 33x24 | 1x1 | 16,0 |
| b06-roca.png | roca | base | 32x30 | 1x1 | 16,-8 |
| b07-roca-honda.png | roca honda | base | 32x31 | 1x1 | 16,-22 |
| b08-muro-izq.png | muro izq. | base | 22x29 | 1x1 | 16,19 |
| b09-muro-der.png | muro der. | base | 21x29 | 1x1 | 5,19 |
| b10-muro-izq-bajo.png | muro izq. bajo | base | 22x23 | 1x1 | 16,13 |
| b11-muro-der-bajo.png | muro der. bajo | base | 21x23 | 1x1 | 5,13 |
| b12-esquina.png | esquina | base | 32x34 | 1x1 | 16,24 |
| b13-arco-izq.png | arco izq. | base | 22x40 | 1x1 | 16,30 |
| b14-arco-der.png | arco der. | base | 21x40 | 1x1 | 5,30 |
| b15-puerta-izq.png | puerta izq. | base | 22x40 | 1x1 | 16,30 |
| b16-puerta-der.png | puerta der. | base | 21x40 | 1x1 | 5,30 |
| b17-remate-izq.png | remate izq. | base | 22x23 | 1x1 | 16,13 |
| b18-remate-der.png | remate der. | base | 21x23 | 1x1 | 5,13 |
| b19-escalera-izq.png | escalera izq. | base | 49x44 | 1x2 | 32,-4 |
| b20-escalera-der.png | escalera der. | base | 49x44 | 2x1 | 16,-4 |
| b21-reja-izq.png | reja izq. | base | 17x35 | 1x1 | 16,28 |
| b22-reja-der.png | reja der. | base | 17x35 | 1x1 | 0,28 |
| b23-antorcha-izq.png | antorcha izq. | base | 3x7 | muro | 3,15 |
| b24-antorcha-der.png | antorcha der. | base | 3x7 | muro | -2,15 |
| b25-pilar.png | pilar | base | 22x41 | 1x1 | 11,27 |
| b26-halo-antorcha.png | halo de antorcha | base | 25x23 | luz | 12,11 |
| b27-luz-ambar.png | luz ámbar | base | 185x101 | luz | 92,49 |
| b28-luz-verde.png | luz verde | base | 185x101 | luz | 92,49 |
| b29-luz-roja.png | luz roja | base | 185x101 | luz | 92,49 |
| b30-luz-azul.png | luz azul | base | 185x101 | luz | 92,49 |
| b31-placa-recuentos.png | placa de recuentos | base | 40x14 | muro | 17,12 |
| b32-halo-verde.png | halo verde | base | 25x23 | luz | 12,11 |
| b33-halo-azul.png | halo azul | base | 25x23 | luz | 12,11 |
| b34-halo-rojo.png | halo rojo | base | 25x23 | luz | 12,11 |
| b35-halo-ambar.png | halo ámbar | base | 25x23 | luz | 12,11 |
| b36-insignia-mas-n.png | insignia +n | base | 12x9 | marca | 6,4 |
| b37-cifras.png | cifras 0-9 | base | 39x5 | marca | 0,0 |
| o01-jaula-de-hierro.png | jaula de hierro | objeto · mazmorra | 28x38 | 1x1 | 14,22 |
| o02-cofre.png | cofre | objeto · mazmorra | 24x20 | 1x1 | 12,5 |
| o03-grilletes.png | grilletes | objeto · mazmorra | 9x17 | muro | 1,12 |
| o04-lecho-de-paja.png | lecho de paja | objeto · mazmorra | 40x24 | 2x1 | 12,1 |
| o05-calavera.png | calavera | objeto · calaveras | 14x11 | 1x1 | 7,0 |
| o06-pila-de-calaveras.png | pila de calaveras | objeto · calaveras | 25x21 | 1x1 | 13,6 |
| o07-huesos-cruzados.png | huesos cruzados | objeto · calaveras | 16x12 | 1x1 | 8,0 |
| o08-calavera-con-vela.png | calavera con vela | objeto · calaveras | 14x16 | 1x1 | 7,5 |
| o09-circulo-magico.png | círculo mágico | objeto · hechizos | 42x22 | 2x2 | 21,-5 |
| o10-atril-con-grimorio.png | atril con grimorio | objeto · hechizos | 18x30 | 1x1 | 9,16 |
| o11-bola-de-cristal.png | bola de cristal | objeto · hechizos | 18x20 | 1x1 | 9,6 |
| o12-caldero.png | caldero | objeto · hechizos | 23x18 | 1x1 | 13,4 |
| o13-mesa-larga.png | mesa larga | objeto · mesas | 45x32 | 2x1 | 14,8 |
| o14-mesa-con-vela.png | mesa con vela | objeto · mesas | 23x20 | 1x1 | 11,6 |
| o15-banco.png | banco | objeto · mesas | 37x24 | 2x1 | 10,2 |
| o16-estanteria.png | estantería | objeto · mesas | 22x36 | 1x1 | 10,22 |
| o17-potro.png | potro | objeto · torturas | 44x33 | 2x1 | 14,9 |
| o18-cepo.png | cepo | objeto · torturas | 23x30 | 1x1 | 12,15 |
| o19-doncella-de-hierro.png | doncella de hierro | objeto · torturas | 22x37 | 1x1 | 11,23 |
| o20-brasero.png | brasero | objeto · torturas | 21x23 | 1x1 | 10,10 |
| o21-mancha-de-sangre.png | mancha de sangre | objeto · sangre | 19x6 | 1x1 | 10,-6 |
| o22-charco-de-sangre.png | charco de sangre | objeto · sangre | 41x17 | 2x2 | 21,-8 |
| o23-rastro-de-sangre.png | rastro de sangre | objeto · sangre | 31x16 | 2x1 | 9,-4 |
| o24-barril.png | barril | objeto · barriles | 19x15 | 1x1 | 10,2 |
| o25-barril-tumbado.png | barril tumbado | objeto · barriles | 22x12 | 1x1 | 12,-2 |
| o26-pila-de-barriles.png | pila de barriles | objeto · barriles | 28x29 | 1x1 | 15,13 |
| o27-caja-de-madera.png | caja de madera | objeto · barriles | 24x22 | 1x1 | 12,7 |
| o28-frasco-rojo.png | frasco rojo | objeto · pociones | 12x11 | 1x1 | 6,0 |
| o29-botella-azul.png | botella azul | objeto · pociones | 10x11 | 1x1 | 5,1 |
| o30-estante-de-pociones.png | estante de pociones | objeto · pociones | 22x29 | 1x1 | 10,15 |
