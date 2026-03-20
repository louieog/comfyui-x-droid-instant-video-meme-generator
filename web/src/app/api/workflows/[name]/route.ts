import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile } from "fs/promises";
import path from "path";
import { PATHS } from "@/lib/paths";

export async function GET(
  _request: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  try {
    const { name } = await params;

    if (name.includes("..") || name.includes("/")) {
      return NextResponse.json({ error: "Invalid name" }, { status: 400 });
    }

    const apiPath = path.join(PATHS.workflows, `${name}-api.json`);
    const manifestPath = path.join(PATHS.workflows, `${name}-manifest.json`);

    let api = null;
    let manifest = null;

    try {
      const raw = await readFile(apiPath, "utf-8");
      api = JSON.parse(raw);
    } catch {
      return NextResponse.json(
        { error: "Workflow not found" },
        { status: 404 }
      );
    }

    try {
      const raw = await readFile(manifestPath, "utf-8");
      manifest = JSON.parse(raw);
    } catch {
      // Manifest is optional
    }

    return NextResponse.json({ name, api, manifest });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read workflow", detail: String(error) },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ name: string }> }
) {
  try {
    const { name } = await params;

    if (name.includes("..") || name.includes("/")) {
      return NextResponse.json({ error: "Invalid name" }, { status: 400 });
    }

    const body = await request.json();
    const { api, manifest } = body;

    if (api) {
      await writeFile(
        path.join(PATHS.workflows, `${name}-api.json`),
        JSON.stringify(api, null, 2),
        "utf-8"
      );
    }

    if (manifest) {
      await writeFile(
        path.join(PATHS.workflows, `${name}-manifest.json`),
        JSON.stringify(manifest, null, 2),
        "utf-8"
      );
    }

    return NextResponse.json({ name, updated: true });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to update workflow", detail: String(error) },
      { status: 500 }
    );
  }
}
