# Comic Placement Check Runtime Prompt

The attached image is ONE comic page. Each transcribed piece of lettering is framed in RED with its number in a yellow label. Below is what each number is supposed to contain. Your job is only to check WHERE each one is: does the red frame with that number enclose exactly that lettering?

REGIONS (number, kind, the lettering that should be inside that frame):
{{REGIONS}}

For every number answer "ok": true when its frame encloses that lettering (small offsets are fine). Answer "ok": false when the frame is on other lettering, on art, or misses most of that lettering, and then give "box": [x0, y0, x1, y1] tightly around where that lettering really is, on a 0..1000 grid over the whole page (x to the right, y downward). Look carefully: the same words can appear twice on a page, and neighbouring balloons in a crowded panel are easy to confuse.

Output ONLY one JSON object, no commentary and no code fences, with every number exactly once:
{"regions": [{"number": 1, "ok": true}, {"number": 2, "ok": false, "box": [120, 640, 260, 700]}]}
