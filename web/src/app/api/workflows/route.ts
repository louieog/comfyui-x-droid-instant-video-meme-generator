import { NextResponse } from "next/server";
import { readdir } from "fs/promises";
import { PATHS } from "@/lib/paths";

export async function GET() {
  try {
    const entries = await readdir(PATHS.workflows);

    // Find workflow pairs (name-api.json + name-manifest.json)
    const apiFiles = entries.filter((f) => f.endsWith("-api.json"));
    const workflows = apiFiles.map((apiFile) => {
      const name = apiFile.replace("-api.json", "");
      const manifestFile = `${name}-manifest.json`;
      const hasManifest = entries.includes(manifestFile);

      return {
        name,
        apiFile,
        manifestFile: hasManifest ? manifestFile : null,
        hasManifest,
      };
    });

    return NextResponse.json(workflows);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to list workflows", detail: String(error) },
      { status: 500 }
    );
  }
}
