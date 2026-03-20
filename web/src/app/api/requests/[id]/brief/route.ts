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

    const briefPath = path.join(PATHS.briefs, `${id}.json`);

    try {
      const raw = await readFile(briefPath, "utf-8");
      return NextResponse.json(JSON.parse(raw));
    } catch {
      return NextResponse.json(
        { error: "Brief not found" },
        { status: 404 }
      );
    }
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
    const briefPath = path.join(PATHS.briefs, `${id}.json`);

    await mkdir(PATHS.briefs, { recursive: true });
    await writeFile(briefPath, JSON.stringify(body, null, 2), "utf-8");

    return NextResponse.json(body);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to update brief", detail: String(error) },
      { status: 500 }
    );
  }
}
