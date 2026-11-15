# The theme's 3D parts

`scene.py` builds and renders, in Blender, the parts of the look that need real depth:

- `bg_system.jpg`, `bg_list.jpg`: the inside of a huge globe covered in a repeated cell tile, seen
  from near its middle, looking at one pole (the tunnel of cells behind the menus).
- `rings_a.png`: the four-fingered metal claw that holds the orb.
- `rings_b.png`: the notched metal ring round it (the theme turns it a little on each move).

    blender -b -P tools/blender/scene.py -- files/theme/art

`cell_tile.png` and the globe's set-up (a sphere of radius 500, the tile repeated 50 times round
and 25 times from pole to pole, a 60 degree camera near the middle looking at a pole) come from
Austin Baccus's Unity recreation of the classic dashboard background,
https://github.com/austinbaccus/xbox-original-dashboard, released under CC0 1.0.
The claw and ring are modelled here.
