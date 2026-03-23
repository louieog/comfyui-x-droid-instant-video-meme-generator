import { NextResponse } from "next/server";
import { readdir, readFile } from "fs/promises";
import path from "path";
import { PATHS } from "@/lib/paths";

function normalizeMetadata(m: Record<string, unknown>, date: string, dirPath: string) {
  const slug =
    (m.slug as string) ||
    ((m.concept as string) || "unknown")
      .toLowerCase()
      .replace(/[^a-z0-9]+/g, "-")
      .replace(/^-|-$/g, "")
      .slice(0, 60);

  let files: Record<string, string> = {};
  if (m.files) {
    files = m.files as Record<string, string>;
  } else if (m.outputs) {
    const outputs = m.outputs as Record<string, Record<string, string>>;
    if (outputs["16x9"]?.file) files["16x9"] = outputs["16x9"].file;
    if (outputs["9x16"]?.file) files["9x16"] = outputs["9x16"].file;
    if (m.thumbnails) {
      const thumbs = m.thumbnails as Record<string, string>;
      files.thumbnail = thumbs["16x9"] || thumbs["9x16"] || "";
    }
  }

  const platform_specs = (m.platform_specs as Record<string, unknown>) || {
    tiktok: { aspect: "9:16", file: files["9x16"] || "", max_duration: 180 },
    reels: { aspect: "9:16", file: files["9x16"] || "", max_duration: 90 },
    shorts: { aspect: "9:16", file: files["9x16"] || "", max_duration: 60 },
    youtube: { aspect: "16:9", file: files["16x9"] || "" },
  };

  return {
    date,
    slug,
    concept: (m.concept as string) || "Untitled",
    format: (m.format as string) || "unknown",
    style: (m.style as string) || "unknown",
    duration_seconds: (m.duration_seconds as number) || 0,
    files,
    suggested_caption: (m.suggested_caption as string) || "",
    suggested_hashtags: (m.suggested_hashtags as string[]) || [],
    platform_specs,
    generation_log: m.generation_log || {},
    assembly_notes: m.assembly_notes || null,
  };
}

export async function GET() {
  try {
    const entries = await readdir(PATHS.output, { withFileTypes: true });
    const dateDirs = entries.filter(
      (e) => e.isDirectory() && /^\d{4}-\d{2}-\d{2}$/.test(e.name)
    );

    const outputs = [];

    for (const dir of dateDirs) {
      const dirPath = path.join(PATHS.output, dir.name);

      // Read ALL json files in this directory that look like metadata
      let dirFiles: string[] = [];
      try {
        dirFiles = await readdir(dirPath);
      } catch {
        continue;
      }

      const metadataFiles = dirFiles.filter(
        (f) => f === "metadata.json" || f.endsWith("-metadata.json")
      );

      // If no metadata files found, scan for videos and create a basic entry
      if (metadataFiles.length === 0) {
        const videos = dirFiles.filter((f) => f.endsWith(".mp4"));
        if (videos.length > 0) {
          const thumbDir = dirFiles.includes("thumbnails") ? "thumbnails" : "";
          let thumbnail = "";
          if (thumbDir) {
            try {
              const thumbFiles = await readdir(path.join(dirPath, "thumbnails"));
              if (thumbFiles.length > 0) thumbnail = `thumbnails/${thumbFiles[0]}`;
            } catch { /* skip */ }
          }
          const file16x9 = videos.find((v) => v.includes("16x9")) || "";
          const file9x16 = videos.find((v) => v.includes("9x16")) || "";
          outputs.push({
            date: dir.name,
            slug: file16x9.replace(/-16x9\.mp4$/, "") || "unknown",
            concept: file16x9.replace(/-16x9\.mp4$/, "").replace(/-/g, " ") || "Untitled",
            format: "unknown",
            style: "unknown",
            duration_seconds: 0,
            files: { "16x9": file16x9, "9x16": file9x16, thumbnail },
            suggested_caption: "",
            suggested_hashtags: [],
            platform_specs: {},
            generation_log: {},
            assembly_notes: null,
          });
        }
        continue;
      }

      for (const metaFile of metadataFiles) {
        try {
          const raw = await readFile(path.join(dirPath, metaFile), "utf-8");
          const m = JSON.parse(raw);
          const normalized = normalizeMetadata(m, dir.name, dirPath);

          // Derive a file prefix from the metadata filename for matching
          // e.g. "foo-bar-metadata.json" -> "foo-bar" which matches "foo-bar-16x9.mp4"
          const filePrefix = metaFile === "metadata.json"
            ? null
            : metaFile.replace(/-?metadata\.json$/, "");

          // If files map is still empty, try to find videos
          if (!normalized.files["16x9"] && !normalized.files["9x16"]) {
            const mp4s = dirFiles.filter((f) => f.endsWith(".mp4"));

            if (filePrefix) {
              // Match by metadata filename prefix
              normalized.files["16x9"] = mp4s.find((f) => f.startsWith(filePrefix) && f.includes("16x9")) || "";
              normalized.files["9x16"] = mp4s.find((f) => f.startsWith(filePrefix) && f.includes("9x16")) || "";
            }

            // Fallback: match by slug prefix
            if (!normalized.files["16x9"] && !normalized.files["9x16"]) {
              const slugPrefix = normalized.slug.slice(0, 20);
              normalized.files["16x9"] = mp4s.find((f) => f.includes("16x9") && f.includes(slugPrefix)) || "";
              normalized.files["9x16"] = mp4s.find((f) => f.includes("9x16") && f.includes(slugPrefix)) || "";
            }

            // Last resort: try to match by excluding videos already claimed by other metadata files
            if (!normalized.files["16x9"]) {
              // Find prefixes claimed by *-metadata.json files
              const claimedPrefixes = dirFiles
                .filter((f) => f.endsWith("-metadata.json"))
                .map((f) => f.replace(/-?metadata\.json$/, ""));
              const unclaimed16 = mp4s.filter(
                (f) => f.includes("16x9") && !claimedPrefixes.some((p) => f.startsWith(p))
              );
              const unclaimed9 = mp4s.filter(
                (f) => f.includes("9x16") && !claimedPrefixes.some((p) => f.startsWith(p))
              );
              if (unclaimed16.length === 1) normalized.files["16x9"] = unclaimed16[0];
              if (unclaimed9.length === 1) normalized.files["9x16"] = unclaimed9[0];
            }
          }

          // Find thumbnail
          if (!normalized.files.thumbnail) {
            try {
              const thumbFiles = await readdir(path.join(dirPath, "thumbnails"));
              let match: string | undefined;
              if (filePrefix) {
                match = thumbFiles.find((t) => t.startsWith(filePrefix));
              }
              if (!match) {
                match = thumbFiles.find((t) => t.includes(normalized.slug.slice(0, 20)));
              }
              if (!match && thumbFiles.length > 0) {
                match = thumbFiles[0];
              }
              if (match) normalized.files.thumbnail = `thumbnails/${match}`;
            } catch { /* no thumbnails dir */ }
          }

          outputs.push(normalized);
        } catch {
          // Skip invalid metadata files
        }
      }
    }

    // Deduplicate by slug (in case metadata.json and *-metadata.json describe the same video)
    const seen = new Set<string>();
    const dedupedOutputs = outputs.filter((o) => {
      const key = `${o.date}-${o.slug}`;
      if (seen.has(key)) return false;
      seen.add(key);
      return true;
    });

    dedupedOutputs.sort((a, b) => b.date.localeCompare(a.date));

    return NextResponse.json({ outputs: dedupedOutputs });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read outputs", detail: String(error) },
      { status: 500 }
    );
  }
}
