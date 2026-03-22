import { NextRequest, NextResponse } from "next/server";
import { readdir, readFile, writeFile, mkdir } from "fs/promises";
import { spawn } from "child_process";
import path from "path";
import { randomUUID } from "crypto";
import { PATHS } from "@/lib/paths";

export async function GET() {
  try {
    const requests: Array<{ id: string; type: "request" | "brief"; data: unknown }> = [];

    // Read request files
    try {
      const reqEntries = await readdir(PATHS.requests);
      for (const file of reqEntries) {
        if (!file.endsWith(".json")) continue;
        try {
          const raw = await readFile(path.join(PATHS.requests, file), "utf-8");
          requests.push({
            id: path.basename(file, ".json"),
            type: "request",
            data: JSON.parse(raw),
          });
        } catch {
          // Skip invalid files
        }
      }
    } catch {
      // requests dir may not exist
    }

    // Read brief files
    try {
      const briefEntries = await readdir(PATHS.briefs);
      for (const file of briefEntries) {
        if (!file.endsWith(".json")) continue;
        try {
          const raw = await readFile(path.join(PATHS.briefs, file), "utf-8");
          requests.push({
            id: path.basename(file, ".json"),
            type: "brief",
            data: JSON.parse(raw),
          });
        } catch {
          // Skip invalid files
        }
      }
    } catch {
      // briefs dir may not exist
    }

    return NextResponse.json(requests);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to list requests", detail: String(error) },
      { status: 500 }
    );
  }
}

export async function POST(request: NextRequest) {
  try {
    const body = await request.json();

    const { concept, format, style, duration_target, duration, model_overrides, modelOverrides, referenceImage } = body;
    const dur = duration_target || duration;
    const models = model_overrides || modelOverrides;

    if (!concept) {
      return NextResponse.json(
        { error: "concept is required" },
        { status: 400 }
      );
    }

    const id = randomUUID();
    const requestData = {
      id,
      concept,
      format: format || "skit",
      style: style || "absurdist",
      duration_target_seconds: dur || 30,
      model_overrides: models || {},
      reference_image: referenceImage || null,
      priority: "normal",
      created_at: new Date().toISOString(),
    };

    await mkdir(PATHS.requests, { recursive: true });
    await writeFile(
      path.join(PATHS.requests, `${id}.json`),
      JSON.stringify(requestData, null, 2),
      "utf-8"
    );

    // Trigger pipeline in background
    const script = path.join(PATHS.root, "scripts", "run-pipeline.sh");
    const child = spawn("bash", [script, id], {
      cwd: PATHS.root,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PATH: `/Users/orlando/.local/bin:${process.env.PATH}` },
    });
    child.unref();

    // Write initial status
    await writeFile(
      path.join(PATHS.requests, `${id}.status.json`),
      JSON.stringify({ request_id: id, status: "generating", stage: "meme-scout", detail: "Pipeline started..." }, null, 2),
      "utf-8"
    );

    return NextResponse.json({ ...requestData, pipeline: "started" }, { status: 201 });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to create request", detail: String(error) },
      { status: 500 }
    );
  }
}
