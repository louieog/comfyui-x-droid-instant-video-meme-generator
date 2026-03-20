import { NextResponse } from "next/server";
import { getAvailableModels } from "@/lib/comfy";

export async function GET() {
  try {
    const models = await getAvailableModels();
    return NextResponse.json(models);
  } catch (error) {
    return NextResponse.json(
      { error: "Failed to fetch models", detail: String(error) },
      { status: 500 }
    );
  }
}
