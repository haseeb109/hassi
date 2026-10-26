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
- Aap ki settings aur prompts browser mein yaad rehte hain

## Agar image na bane

- **"Access nahi mila"**: tool ko Gemini Canvas ke andar chalayein. Bahar (normal browser mein) is ko API key chahiye hoti hai.
- **Limit hit (429)**: thori der ruk kar **Retry Failed** dabayein, ya Advanced mein Parallel ko 1 kar dein.
- **Safety filter**: prompt ke alfaaz thore badal kar Regenerate karein.
- Agar Google model ka naam badal de to **Advanced settings** mein model ka naya naam likh dein.
