import { NextResponse } from "next/server";
import { readdir, readFile } from "fs/promises";
import path from "path";
import { PATHS } from "@/lib/paths";

export async function GET() {
  try {
    const entries = await readdir(PATHS.output, { withFileTypes: true });
    const dateDirs = entries.filter(
      (e) => e.isDirectory() && /^\d{4}-\d{2}-\d{2}$/.test(e.name)
    );

    const outputs = [];

    for (const dir of dateDirs) {
      const dirPath = path.join(PATHS.output, dir.name);
      const metadataPath = path.join(dirPath, "metadata.json");

      try {
        const raw = await readFile(metadataPath, "utf-8");
        const metadata = JSON.parse(raw);
        outputs.push({
          date: dir.name,
          metadata,
        });
      } catch {
        // Skip dirs without valid metadata
      }
    }

    // Sort newest first
    outputs.sort((a, b) => b.date.localeCompare(a.date));

    return NextResponse.json(outputs);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read outputs", detail: String(error) },
      { status: 500 }
    );
  }
}
