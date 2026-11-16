# The theme's 3D parts

`scene.py` builds and renders, in Blender, the parts of the look that need real depth:

- `bg_system.jpg`, `bg_list.jpg`: the inside of a huge globe covered in a repeated cell tile, seen
  from near its middle, looking at one pole (the tunnel of cells behind the menus).
- `rings_a.png`: what holds the orb (drawn behind it): a thick ring with four loop clips, and four curved, see-through
  shell arms that leave the clips, reach the orb's edge and curl over its front, gripping it. The theme turns it a quarter
  turn on each move, so all four quarters are alike and it is lit evenly.
- `row_arm.png`: the small metal arm joining each menu row's pod to its bar, seen from the side
  (`art.py` builds the rows from it, so render this first).

    blender -b -P tools/blender/scene.py -- files/theme/art      # then: python3 tools/art.py files/theme

`cell_tile.png` and the globe's set-up (a sphere of radius 500, the tile repeated 50 times round
and 25 times from pole to pole, a 60 degree camera near the middle looking at a pole) come from
Austin Baccus's Unity recreation of the classic dashboard background,
https://github.com/austinbaccus/xbox-original-dashboard, released under CC0 1.0.
The holder is modelled here, after the layout of the classic dashboard's main menu (studied, not copied:
none of its meshes or textures are in this repository).
