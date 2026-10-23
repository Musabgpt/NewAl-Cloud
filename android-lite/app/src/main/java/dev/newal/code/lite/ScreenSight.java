package dev.newal.code.lite;

import android.content.Context;
import android.graphics.Bitmap;
import android.graphics.BitmapFactory;

import org.json.JSONObject;

import java.io.File;
import java.io.FileOutputStream;

/**
 * A magnified part of a screenshot, for screen_tap (phone_sight.py): after a vision model points at a target on the
 * whole screen, it looks again at this crop around that point for the exact spot. Only the app's own screenshots
 * (its cache folder) are read.
 */
final class ScreenSight {
    private ScreenSight() {
    }

    static JSONObject crop(Context ctx, JSONObject a) throws Exception {
        File cache = ctx.getCacheDir().getCanonicalFile();
        File in = new File(a.optString("path")).getCanonicalFile();
        if (!cache.equals(in.getParentFile()) || !in.getName().startsWith("musabai-screen-")) {
            throw new SecurityException("only the app's own screenshots can be cropped");
        }
        Bitmap full = BitmapFactory.decodeFile(in.getPath());
        if (full == null) throw new IllegalArgumentException("not an image: " + in.getName());
        File out = new File(cache, "musabai-crop-" + System.currentTimeMillis() + ".jpg");
        int w, h;
        try {
            int x = Math.max(0, Math.min(a.optInt("x"), full.getWidth() - 1));
            int y = Math.max(0, Math.min(a.optInt("y"), full.getHeight() - 1));
            w = Math.max(1, Math.min(a.optInt("w", full.getWidth()), full.getWidth() - x));
            h = Math.max(1, Math.min(a.optInt("h", full.getHeight()), full.getHeight() - y));
            Bitmap part = Bitmap.createBitmap(full, x, y, w, h);
            // magnified up to the size a vision model is shown (at most 3 times), never shrunk below the crop
            float k = Math.max(1f, Math.min(3f, a.optInt("max", 720) / (float) Math.max(w, h)));
            Bitmap scaled = k > 1f ? Bitmap.createScaledBitmap(part, Math.round(w * k), Math.round(h * k), true) : part;
            try (FileOutputStream stream = new FileOutputStream(out)) {
                if (!scaled.compress(Bitmap.CompressFormat.JPEG, 82, stream))
                    throw new IllegalStateException("crop encoding failed");
            } finally {
                if (scaled != part) scaled.recycle();
                if (part != full) part.recycle();
            }
        } finally {
            full.recycle();
        }
        long now = System.currentTimeMillis();
        File[] old = cache.listFiles((dir, name) -> name.startsWith("musabai-crop-") && !name.equals(out.getName()));
        if (old != null) for (File f : old) if (f.lastModified() < now - 600_000L) f.delete();
        JSONObject o = Phone.ok("cropped: " + out.getAbsolutePath());
        o.put("path", out.getAbsolutePath());
        o.put("width", w);
        o.put("height", h);
        return o;
    }
}
