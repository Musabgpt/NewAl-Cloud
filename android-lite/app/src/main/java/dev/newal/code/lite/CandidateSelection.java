package dev.newal.code.lite;

import org.json.JSONObject;

import java.io.File;
import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.nio.file.FileVisitResult;
import java.nio.file.Files;
import java.nio.file.LinkOption;
import java.nio.file.Path;
import java.nio.file.SimpleFileVisitor;
import java.nio.file.attribute.BasicFileAttributes;
import java.security.MessageDigest;
import java.util.ArrayList;
import java.util.List;

/** Validates saved evolution evidence before adding a candidate to Python's import path. */
final class CandidateSelection {
    private CandidateSelection() { }

    /** Invalid, stale or unreadable selections always leave the packaged engine selected. */
    static File select(File home, String packagedBuild) {
        if (home == null || packagedBuild == null || packagedBuild.isEmpty()) return null;
        try {
            if (Files.isSymbolicLink(home.toPath())) return null;
            Path root = home.getCanonicalFile().toPath();
            directory(root);
            Path config = root.resolve(".newal-code");
            directory(config);
            Path evolution = config.resolve("evolution");
            directory(evolution);
            JSONObject active = readJson(evolution.resolve("active.json"));
            String id = string(active, "id");
            if (id == null || !id.matches("[0-9a-f]{24}")
                    || !packagedBuild.equals(string(active, "packaged_build"))) return null;

            Path candidates = evolution.resolve("candidates");
            directory(candidates);
            Path candidate = candidates.resolve(id);
            directory(candidate);
            try (java.nio.file.DirectoryStream<Path> entries = Files.newDirectoryStream(candidate)) {
                for (Path entry : entries) {
                    String name = entry.getFileName().toString();
                    if (!"newal_code".equals(name) && !"test-home".equals(name)) return null;
                    directory(entry);
                }
            }
            // A marker must name this exact candidate, without traversal or alternate spellings.
            File expected = new File(home, ".newal-code/evolution/candidates/" + id);
            if (!expected.getAbsolutePath().equals(string(active, "path"))
                    || !candidate.toFile().equals(expected.getCanonicalFile())) return null;

            JSONObject record = readJson(evolution.resolve(id + ".json"));
            String verifiedDigest = string(record, "verified_digest");
            if (!id.equals(string(record, "id")) || !"verified".equals(string(record, "status"))
                    || !packagedBuild.equals(string(record, "packaged_build"))
                    || verifiedDigest == null || !verifiedDigest.matches("[0-9a-f]{64}")) return null;

            Path engine = candidate.resolve("newal_code");
            directory(engine);
            regularFile(engine.resolve("__init__.py"));
            regularFile(engine.resolve("server.py"));
            List<Path> files = new ArrayList<>();
            // Check the entire candidate, including ignored cache/git directories and siblings.
            Files.walkFileTree(candidate, new SimpleFileVisitor<Path>() {
                @Override public FileVisitResult preVisitDirectory(Path dir, BasicFileAttributes attrs)
                        throws IOException {
                    if (attrs.isSymbolicLink() || !attrs.isDirectory()) throw new IOException("Unsafe directory");
                    return FileVisitResult.CONTINUE;
                }

                @Override public FileVisitResult visitFile(Path file, BasicFileAttributes attrs)
                        throws IOException {
                    if (attrs.isSymbolicLink() || !attrs.isRegularFile()) throw new IOException("Unsafe file");
                    if (file.startsWith(engine) && !ignored(engine.relativize(file))) files.add(file);
                    return FileVisitResult.CONTINUE;
                }
            });

            // pathlib orders by path components and Unicode code points, not UTF-16 or flat paths.
            files.sort((left, right) -> comparePaths(engine.relativize(left), engine.relativize(right)));
            MessageDigest digest = MessageDigest.getInstance("SHA-256");
            byte[] buffer = new byte[32768];
            for (Path file : files) {
                String relative = engine.relativize(file).toString().replace(File.separatorChar, '/');
                digest.update(relative.getBytes(StandardCharsets.UTF_8));
                try (InputStream input = Files.newInputStream(file, LinkOption.NOFOLLOW_LINKS)) {
                    for (int count; (count = input.read(buffer)) != -1; ) digest.update(buffer, 0, count);
                }
            }
            StringBuilder actual = new StringBuilder(64);
            for (byte value : digest.digest()) {
                actual.append(Character.forDigit((value & 255) >>> 4, 16));
                actual.append(Character.forDigit(value & 15, 16));
            }
            return verifiedDigest.equals(actual.toString()) ? candidate.toFile() : null;
        } catch (Exception ignored) {
            return null;
        }
    }

    private static JSONObject readJson(Path path) throws Exception {
        regularFile(path);
        return new JSONObject(new String(Files.readAllBytes(path), StandardCharsets.UTF_8));
    }

    private static String string(JSONObject object, String key) {
        Object value = object.opt(key);
        return value instanceof String ? (String) value : null;
    }

    private static void directory(Path path) throws IOException {
        if (!Files.isDirectory(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Missing directory");
    }

    private static void regularFile(Path path) throws IOException {
        if (!Files.isRegularFile(path, LinkOption.NOFOLLOW_LINKS)) throw new IOException("Missing file");
    }

    private static boolean ignored(Path path) {
        for (Path part : path) {
            if ("__pycache__".equals(part.toString()) || ".git".equals(part.toString())) return true;
        }
        return false;
    }

    private static int comparePaths(Path left, Path right) {
        for (int i = 0; i < Math.min(left.getNameCount(), right.getNameCount()); i++) {
            int order = compareCodePoints(left.getName(i).toString(), right.getName(i).toString());
            if (order != 0) return order;
        }
        return Integer.compare(left.getNameCount(), right.getNameCount());
    }

    private static int compareCodePoints(String left, String right) {
        int l = 0, r = 0;
        while (l < left.length() && r < right.length()) {
            int a = left.codePointAt(l), b = right.codePointAt(r);
            if (a != b) return Integer.compare(a, b);
            l += Character.charCount(a);
            r += Character.charCount(b);
        }
        return Integer.compare(left.length() - l, right.length() - r);
    }
}
