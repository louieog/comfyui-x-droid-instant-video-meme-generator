import { NextRequest, NextResponse } from "next/server";
import { readFile, writeFile } from "fs/promises";
import { PATHS } from "@/lib/paths";

export async function GET() {
  try {
    const raw = await readFile(PATHS.seedList, "utf-8");
    return NextResponse.json(JSON.parse(raw));
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to read seed list", detail: String(error) },
      { status: 500 }
    );
  }
}

export async function PUT(request: NextRequest) {
  try {
    const body = await request.json();
    await writeFile(PATHS.seedList, JSON.stringify(body, null, 2), "utf-8");
    return NextResponse.json(body);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to update seed list", detail: String(error) },
      { status: 500 }
    );
  }
}
