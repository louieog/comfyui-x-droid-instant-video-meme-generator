"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Select } from "@/components/ui/select";
import { Plus, Film, Search } from "lucide-react";
import type { VideoOutput } from "@/lib/types";

export default function Dashboard() {
  const [outputs, setOutputs] = useState<VideoOutput[]>([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [formatFilter, setFormatFilter] = useState("");

  useEffect(() => {
    fetch("/api/outputs")
      .then((r) => r.json())
      .then((data) => setOutputs(data.outputs || []))
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  const filtered = outputs.filter((o) => {
    const matchesSearch =
      !search ||
      o.concept.toLowerCase().includes(search.toLowerCase()) ||
      o.suggested_caption?.toLowerCase().includes(search.toLowerCase());
    const matchesFormat = !formatFilter || o.format === formatFilter;
    return matchesSearch && matchesFormat;
  });

  const formats = [...new Set(outputs.map((o) => o.format))];

  function getStatusColor(log: VideoOutput["generation_log"]) {
    const statuses = [log.images?.status, log.tts?.status, log.video?.status, log.lip_sync?.status];
    if (statuses.every((s) => s === "all_success")) return "bg-green-500";
    if (statuses.some((s) => s?.includes("failed"))) return "bg-red-500";
    return "bg-yellow-500";
  }

  return (
    <div>
      <Header
        title="Dashboard"
        description="Your generated content"
        action={
          <Link href="/create">
            <Button>
              <Plus className="w-4 h-4 mr-2" /> New Request
            </Button>
          </Link>
        }
      />

      <div className="flex gap-4 mb-6">
        <div className="relative flex-1 max-w-sm">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-muted-foreground" />
          <Input
            placeholder="Search videos..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="pl-10"
          />
        </div>
        <Select
          options={[{ value: "", label: "All Formats" }, ...formats.map((f) => ({ value: f, label: f }))]}
          value={formatFilter}
          onChange={setFormatFilter}
        />
      </div>

      {loading ? (
        <div className="flex items-center justify-center h-64">
          <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
        </div>
      ) : filtered.length === 0 ? (
        <Card className="flex flex-col items-center justify-center py-20">
          <CardContent className="text-center">
            <Film className="w-16 h-16 text-muted-foreground mb-4 mx-auto" />
            <h3 className="text-lg font-medium mb-2">No videos yet</h3>
            <p className="text-muted-foreground mb-6">Create your first viral video</p>
            <Link href="/create">
              <Button>
                <Plus className="w-4 h-4 mr-2" /> Create Video
              </Button>
            </Link>
          </CardContent>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-6">
          {filtered.map((output) => (
            <Link key={`${output.date}-${output.slug}`} href={`/create/${output.slug}/output`}>
              <Card className="group cursor-pointer hover:border-primary/50 transition-colors overflow-hidden">
                <div className="relative aspect-video bg-secondary">
                  {output.files.thumbnail ? (
                    <img
                      src={`/api/outputs/${output.date}/${output.files.thumbnail}`}
                      alt={output.concept}
                      className="w-full h-full object-cover"
                    />
                  ) : (
                    <div className="w-full h-full bg-gradient-to-br from-primary/20 to-secondary flex items-center justify-center">
                      <Film className="w-12 h-12 text-muted-foreground" />
                    </div>
                  )}
                  <div className="absolute inset-0 bg-black/60 opacity-0 group-hover:opacity-100 transition-opacity flex items-center justify-center">
                    <span className="text-sm font-medium">View Details</span>
                  </div>
                  <div className="absolute top-2 right-2">
                    <div className={`w-2.5 h-2.5 rounded-full ${getStatusColor(output.generation_log)}`} />
                  </div>
                </div>
                <CardContent className="p-4">
                  <h3 className="font-medium text-sm mb-2 line-clamp-1">{output.concept}</h3>
                  <div className="flex flex-wrap gap-1.5 mb-3">
                    <Badge variant="secondary">{output.format}</Badge>
                    <Badge variant="outline">{output.style}</Badge>
                    <Badge variant="outline">{output.duration_seconds}s</Badge>
                  </div>
                  <div className="flex flex-wrap gap-1 mb-3">
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {output.generation_log.video?.model}
                    </Badge>
                    <Badge variant="outline" className="text-[10px] px-1.5 py-0">
                      {output.generation_log.images?.model}
                    </Badge>
                  </div>
                  <p className="text-xs text-muted-foreground line-clamp-1">{output.suggested_caption}</p>
                  <p className="text-xs text-muted-foreground mt-1">{output.date}</p>
                </CardContent>
              </Card>
            </Link>
          ))}
        </div>
      )}
    </div>
  );
}
