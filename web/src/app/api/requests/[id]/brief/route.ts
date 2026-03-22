import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile, mkdir } from "fs/promises";
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

    // Check multiple locations for the brief
    const candidates = [
      path.join(PATHS.requests, `${id}.brief.json`),
      path.join(PATHS.briefs, `${id}.json`),
      path.join(PATHS.briefs, `${id}-brief.json`),
    ];

    for (const p of candidates) {
      try {
        const raw = await readFile(p, "utf-8");
        return NextResponse.json(JSON.parse(raw));
      } catch {
        continue;
      }
    }

    // Also try to find by reading status for slug
    try {
      const statusRaw = await readFile(
        path.join(PATHS.requests, `${id}.status.json`),
        "utf-8"
      );
      const status = JSON.parse(statusRaw);
      if (status.slug) {
        try {
          const raw = await readFile(
            path.join(PATHS.briefs, `${status.slug}-brief.json`),
            "utf-8"
          );
          return NextResponse.json(JSON.parse(raw));
        } catch {
          // not found
        }
      }
    } catch {
      // no status
    }

    return NextResponse.json({ error: "Brief not found" }, { status: 404 });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read brief", detail: String(error) },
      { status: 500 }
    );
  }
}

export async function PUT(
  request: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;

    if (id.includes("..") || id.includes("/")) {
      return NextResponse.json({ error: "Invalid id" }, { status: 400 });
    }

    const body = await request.json();

    // Save to request-keyed path
    await writeFile(
      path.join(PATHS.requests, `${id}.brief.json`),
      JSON.stringify(body, null, 2),
      "utf-8"
    );

    // Also save to briefs dir
    await mkdir(PATHS.briefs, { recursive: true });
    await writeFile(
      path.join(PATHS.briefs, `${id}.json`),
      JSON.stringify(body, null, 2),
      "utf-8"
    );

    // Also save by slug if we know it
    try {
      const statusRaw = await readFile(
        path.join(PATHS.requests, `${id}.status.json`),
        "utf-8"
      );
      const status = JSON.parse(statusRaw);
      if (status.slug) {
        await writeFile(
          path.join(PATHS.briefs, `${status.slug}-brief.json`),
          JSON.stringify(body, null, 2),
          "utf-8"
        );
      }
    } catch {
      // no status, skip slug save
    }

    return NextResponse.json(body);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to update brief", detail: String(error) },
      { status: 500 }
    );
  }
}
