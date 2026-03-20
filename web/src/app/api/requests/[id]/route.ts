import { NextRequest, NextResponse } from "next/server";
import { readFile } from "fs/promises";
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

    let requestData = null;
    let briefData = null;

    // Try to read the request file
    try {
      const raw = await readFile(
        path.join(PATHS.requests, `${id}.json`),
        "utf-8"
      );
      requestData = JSON.parse(raw);
    } catch {
      // Request file may not exist
    }

    // Try to read associated brief
    try {
      const raw = await readFile(
        path.join(PATHS.briefs, `${id}.json`),
        "utf-8"
      );
      briefData = JSON.parse(raw);
    } catch {
      // Brief may not exist
    }

    // Also check for briefs with different naming (e.g. slug-based)
    if (!briefData && requestData) {
      // Try matching by concept slug
    }

    if (!requestData && !briefData) {
      return NextResponse.json({ error: "Request not found" }, { status: 404 });
    }

    return NextResponse.json({
      id,
      request: requestData,
      brief: briefData,
    });
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read request", detail: String(error) },
      { status: 500 }
    );
  }
}
