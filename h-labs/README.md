# H Labs — Bulk Image Studio

Timecode wale prompts se ek saath bohat saari AI images banane ka tool. Yeh **Gemini Canvas ke andar** chalta hai, is liye koi API key nahi lagani padti.

## Gemini mein kaise chalayein

1. [gemini.google.com](https://gemini.google.com) kholein.
2. Neeche **Tools** se **Canvas** select karein.
3. `index.html` file attach karein (ya us ka poora code paste karein), aur saath yeh likhein:
   > Is HTML code ko Canvas mein bilkul waisa hi chalao. Code mein koi change mat karna.
4. Canvas mein **H Labs** khul jayega. Ab prompts paste karein aur **Generate Images** dabayein.
5. Upar **Share** se link bana kar team ya clients ko de sakte hain.

## Prompts ka format

Har line se ek image banti hai. Line ke shuru mein timecode ho to file ka naam wahi ban jata hai:

```
#0-00 Ethan sitting in a cozy cafe, morning light
#0-15 Close up of a steaming coffee cup
0:30 - Ethan walking on a rainy street at night
```

In se `0-00.png`, `0-15.png` aur `0-30.png` banengi. Jis line mein timecode na ho us ka naam `001`, `002`... hoga.

## Features

- **Sizes:** 1:1 (1536×1536), 9:16 Shorts/TikTok (1080×1920), 16:9 YouTube (1920×1080), YouTube Thumbnail (1280×720), 4:3 aur 3:4
- **Character Match:** character ki description, aur chahein to reference photos, taake har image mein wohi chehra aur kapde rahein
- **Style Match:** 10 ready styles (Cinematic, 3D Pixar, Anime, Documentary...), apne notes aur style reference image
- **Engines:** Auto, Imagen ya Nano Banana. Reference image ho to Auto khud Nano Banana use karta hai.
- Ek waqt mein 1 se 4 images, limit (429) aane par khud retry, **Stop**, aur **Retry Failed**
- Har image par View, Regenerate (prompt badal kar), Download aur Remove
- Kai images select karke ek saath download, regenerate ya remove
- **Download ZIP**: saari images timecode naam ke saath

## Thumbnail mode

Sidebar ke upar **Thumbnail** par click karein.

- **Character lock lazmi hai:** kam az kam 1 saaf chehre wali photo daalein. Saare thumbnails usi chehre se banenge.
- **Images per prompt:** har idea ki 1 se 4 images (default 4), taake aap best wali chun sakein.
- **Quality:** 4K (3840×2160), 2K (2560×1440) ya Native. Tool pehle Nano Banana Pro se 4K maangta hai. Woh na mile to 2K, aur phir standard model.
- Har card par likha hota hai ke image asal mein kis size mein bani. Agar "upscaled from…" likha ho to model ne chhoti image di thi aur tool ne usay bada kiya hai.
- **Upload-ready copy:** har thumbnail ki ek chhoti JPG (1280×720 ya 1080×1920) ZIP ke `upload_ready` folder mein, YouTube par seedha upload ke liye.
- 16:9 (YouTube) aur 9:16 (Shorts/TikTok cover) dono.

## AI Quality Check (kharab images pakarna)

Sidebar mein **AI Quality Check** on rakhein (default on).

- Har image banne ke baad Gemini usay dekhta hai: ulti ya ziada ungliyan, bigra chehra, extra ya jure hue log, ajeeb text, prompt se match aur character se match.
- Card par score aata hai, jaise `✓ 9/10`. Kharab image par orange **"⚠ 4/10 · Retry suggested"** aur neeche wajah likhi hoti hai.
- **Auto-retry flagged:** flagged image khud dobara banti hai (1 ya 2 baar). Nayi aur purani mein se jo behtar ho wahi rehti hai.
- **Strictness:** Strict, Normal ya Relaxed.
- **Retry Flagged** button se baqi flagged images ek saath dobara banayein.
- ZIP mein flagged images `flagged/` folder mein alag jati hain, taake editing mein ghalti se na lagein.
- Har check ek chhoti si Gemini request hai, is liye yeh bhi limit mein ginti hai.

## Progress panel aur view

- Upar panel mein: kitne % ho gaye, Done, Speed (images/min), Time left, Checking, Flagged aur Failed.
- **Filters:** All, Ready, Flagged, Failed.
- **Images per row:** `+` se preview bara (kam images per line), `−` se chhota (zyada images per line), ya dropdown se 1 se 10 tak.
- **Hide details** se image ke neeche ka text chhup jata hai aur sirf images dikhti hain.

## Generation Speed

Sidebar ke **Generation Speed** card se speed chunein:

| Preset | Ek saath images | Har image ke darmiyan gap |
|---|---|---|
| Safe | 1 | 6s |
| Normal | 2 | 2s |
| Fast | 4 | 0.5s |
| Turbo | 6 | 0s |

- Dono sliders khud hila kar **Custom** speed bhi bana sakte hain (1-8 images, 0-15s gap).
- Speed batch chalte waqt bhi badal sakte hain, foran lagti hai.
- **Smart alert:** tool pichli 20 images dekhta rehta hai. Limit aaye ya 25% se zyada images fail hon to laal patti aati hai: *"Speed zyada hai, kam karein. Recommended: …"*. **Apply** dabane se speed ek darja kam ho jati hai. Safety filter wali ghaltiyan is mein nahi ginti jatin.
- **Limit test:** progress panel ke neeche likha hota hai ke is session mein kitni images aur requests hui, aur pehli limit kitni images ke baad aur kis speed par aayi. Is se apne Canvas ki asal limit ka andaza lagayein.

## Auto-pause

Limit (429) aate hi tool ruk jata hai, upar countdown dikhata hai aur waqt poora hone par khud dobara shuru ho jata hai. Har baar intezaar thora lamba hota hai, zyada se zyada 15 minute. **Resume now** se foran shuru kar sakte hain. Settings **Advanced** mein hain.

## Agar image na bane

- **"Access nahi mila"**: tool ko Gemini Canvas ke andar chalayein. Bahar (normal browser mein) is ko API key chahiye hoti hai.
- **Limit hit (429)**: thori der ruk kar **Retry Failed** dabayein, ya Advanced mein Parallel ko 1 kar dein.
- **Safety filter**: prompt ke alfaaz thore badal kar Regenerate karein.
- Agar Google model ka naam badal de to **Advanced settings** mein model ka naya naam likh dein.
