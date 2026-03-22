import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile } from "fs/promises";
import { spawn } from "child_process";
import path from "path";
import { PATHS } from "@/lib/paths";

export async function POST(
  _request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    if (id.includes("..") || id.includes("/")) {
      return NextResponse.json({ error: "Invalid id" }, { status: 400 });
    }

    const requestFile = path.join(PATHS.requests, `${id}.json`);
    try {
      await readFile(requestFile, "utf-8");
    } catch {
      return NextResponse.json({ error: "Request not found" }, { status: 404 });
    }

    // Reset status
    await writeFile(
      path.join(PATHS.requests, `${id}.status.json`),
      JSON.stringify(
        { request_id: id, status: "generating", stage: "meme-scout", detail: "Retrying pipeline..." },
        null,
        2
      ),
      "utf-8"
    );

    // Spawn pipeline
    const script = path.join(PATHS.root, "scripts", "run-pipeline.sh");
    const child = spawn("bash", [script, id], {
      cwd: PATHS.root,
      detached: true,
      stdio: ["ignore", "pipe", "pipe"],
      env: { ...process.env, PATH: `/Users/orlando/.local/bin:${process.env.PATH}` },
    });
    child.unref();

    return NextResponse.json({ status: "retrying", request_id: id });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to retry", detail: String(error) },
      { status: 500 }
    );
  }
}
