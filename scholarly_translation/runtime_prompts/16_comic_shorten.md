# Comic Shortening Runtime Prompt

On this comic page some {{T:TARGET}} translations are too long for their balloon or box. The attached image is the page; the regions below are outlined in RED and numbered with their reading order.

Rewrite ONLY the listed regions so each fits: the new text must be no longer than "max_chars" characters and shorter than the current text. Keep the meaning, tone, the speaker's voice, the gender agreement and the notebook names; drop the least important words first, prefer a shorter phrase over cutting off the end.

REGIONS TO SHORTEN:
{{REGIONS}}

Return every listed id exactly once and no other id. Output ONLY one JSON object, no commentary and no code fences:
{"translations": [{"id": "...", "text": "..."}]}
