import { NextRequest, NextResponse } from "next/server";
import { readFile, readdir } from "fs/promises";
import path from "path";
import { PATHS } from "@/lib/paths";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    if (id.includes("..") || id.includes("/")) {
      return NextResponse.json({ error: "Invalid id" }, { status: 400 });
    }

    const logs: Record<string, string> = {};
    const stages = ["meme-scout", "comfy-dispatcher", "assembler"];

    for (const stage of stages) {
      const logFile = path.join(PATHS.requests, `${id}.${stage}.log`);
      try {
        const content = await readFile(logFile, "utf-8");
        logs[stage] = content;
      } catch {
        // Log file doesn't exist yet
      }
    }

    // Also list any output files for this request
    let statusData = null;
    try {
      const raw = await readFile(
        path.join(PATHS.requests, `${id}.status.json`),
        "utf-8"
      );
      statusData = JSON.parse(raw);
    } catch {
      // No status
    }

    // If we have a slug, check for scene assets
    const assets: string[] = [];
    if (statusData?.slug) {
      const scenesDir = path.join(PATHS.output, "scenes", statusData.slug);
      try {
        const files = await readdir(scenesDir);
        for (const f of files) {
          assets.push(f);
        }
      } catch {
        // No assets yet
      }
    }

    return NextResponse.json({ logs, status: statusData, assets });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read logs", detail: String(error) },
      { status: 500 }
    );
  }
}
