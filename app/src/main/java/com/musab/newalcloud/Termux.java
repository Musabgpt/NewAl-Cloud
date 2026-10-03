package com.musab.newalcloud;

import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.os.Build;

import java.net.InetSocketAddress;
import java.net.Socket;

final class Termux {
    static final String PKG = "com.termux";
    static final String PERMISSION = "com.termux.permission.RUN_COMMAND";
    private static final String BASH = "/data/data/com.termux/files/usr/bin/bash";

    private Termux() {}

    static boolean installed(Context c) {
        try { c.getPackageManager().getPackageInfo(PKG, 0); return true; }
        catch (PackageManager.NameNotFoundException e) { return false; }
    }

    static boolean allowed(Context c) {
        try { return c.checkSelfPermission(PERMISSION) == PackageManager.PERMISSION_GRANTED; }
        catch (Exception e) { return false; }
    }

    static boolean up() {
        try (Socket s = new Socket()) {
            s.connect(new InetSocketAddress("127.0.0.1", 8791), 400);
            return true;
        } catch (Exception e) { return false; }
    }

    static void open(Context c) {
        Intent i = c.getPackageManager().getLaunchIntentForPackage(PKG);
        if (i != null) { i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK); c.startActivity(i); }
    }

    static void run(Context c, String command) {
        Intent i = new Intent("com.termux.RUN_COMMAND");
        i.setClassName(PKG, "com.termux.app.RunCommandService");
        i.putExtra("com.termux.RUN_COMMAND_PATH", BASH);
        i.putExtra("com.termux.RUN_COMMAND_ARGUMENTS", new String[]{"-lc", command});
        i.putExtra("com.termux.RUN_COMMAND_WORKDIR", "/data/data/com.termux/files/home");
        i.putExtra("com.termux.RUN_COMMAND_BACKGROUND", true);
        if (Build.VERSION.SDK_INT >= 26) c.startForegroundService(i); else c.startService(i);
    }
}
