"use client";

import { useEffect, useState } from "react";
import { Header } from "@/components/layout/header";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Plus, Save, Trash2, X } from "lucide-react";
import type { SeedList } from "@/lib/types";

interface WorkflowInfo {
  name: string;
  manifest: Record<string, unknown>;
}

export default function SettingsPage() {
  const [seeds, setSeeds] = useState<SeedList | null>(null);
  const [workflows, setWorkflows] = useState<WorkflowInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [newTheme, setNewTheme] = useState("");
  const [newAvoid, setNewAvoid] = useState("");
  const [expandedWf, setExpandedWf] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/api/seeds").then((r) => r.json()),
      fetch("/api/workflows").then((r) => r.json()),
    ])
      .then(([seedData, wfData]) => {
        setSeeds(seedData);
        setWorkflows(wfData.workflows || []);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  async function saveSeedList() {
    if (!seeds) return;
    setSaving(true);
    try {
      await fetch("/api/seeds", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(seeds),
      });
    } catch {
      // handle
    } finally {
      setSaving(false);
    }
  }

  function addTopic() {
    if (!newTheme.trim() || !seeds) return;
    setSeeds({
      ...seeds,
      topics: [...seeds.topics, { theme: newTheme.trim(), notes: "", styles: [] }],
    });
    setNewTheme("");
  }

  function removeTopic(i: number) {
    if (!seeds) return;
    setSeeds({ ...seeds, topics: seeds.topics.filter((_, idx) => idx !== i) });
  }

  function addAvoidItem() {
    if (!newAvoid.trim() || !seeds) return;
    setSeeds({ ...seeds, avoid: [...seeds.avoid, newAvoid.trim()] });
    setNewAvoid("");
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-96">
        <div className="animate-spin w-8 h-8 border-2 border-primary border-t-transparent rounded-full" />
      </div>
    );
  }

  return (
    <div>
      <Header title="Settings" description="Manage seeds, workflows, and preferences" />

      <Tabs defaultValue="seeds">
        <TabsList>
          <TabsTrigger value="seeds">Seed List</TabsTrigger>
          <TabsTrigger value="workflows">Workflow Templates</TabsTrigger>
        </TabsList>

        <TabsContent value="seeds">
          <div className="max-w-3xl space-y-6 mt-6">
            {/* Topics */}
            <Card>
              <CardHeader>
                <div className="flex items-center justify-between">
                  <CardTitle className="text-base">Topics</CardTitle>
                  <Button size="sm" onClick={saveSeedList} disabled={saving}>
                    <Save className="w-4 h-4 mr-1" /> {saving ? "Saving..." : "Save"}
                  </Button>
                </div>
              </CardHeader>
              <CardContent className="space-y-3">
                {seeds?.topics.map((topic, i) => (
                  <div key={i} className="flex items-start gap-3 p-3 bg-secondary/30 rounded-lg">
                    <div className="flex-1">
                      <p className="text-sm font-medium">{topic.theme}</p>
                      <p className="text-xs text-muted-foreground">{topic.notes}</p>
                      <div className="flex gap-1 mt-1">
                        {topic.styles.map((s) => (
                          <Badge key={s} variant="outline" className="text-[10px]">{s}</Badge>
                        ))}
                      </div>
                    </div>
                    <button onClick={() => removeTopic(i)} className="p-1 hover:bg-secondary rounded">
                      <Trash2 className="w-3.5 h-3.5 text-muted-foreground" />
                    </button>
                  </div>
                ))}
                <div className="flex gap-2">
                  <Input
                    value={newTheme}
                    onChange={(e) => setNewTheme(e.target.value)}
                    placeholder="New topic theme..."
                    onKeyDown={(e) => e.key === "Enter" && addTopic()}
                  />
                  <Button variant="secondary" onClick={addTopic}>
                    <Plus className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>

            {/* Avoid List */}
            <Card>
              <CardHeader>
                <CardTitle className="text-base">Avoid List</CardTitle>
              </CardHeader>
              <CardContent>
                <div className="flex flex-wrap gap-2 mb-3">
                  {seeds?.avoid.map((item) => (
                    <Badge key={item} variant="destructive" className="gap-1">
                      {item}
                      <button onClick={() => setSeeds(seeds ? { ...seeds, avoid: seeds.avoid.filter((a) => a !== item) } : seeds)}>
                        <X className="w-3 h-3" />
                      </button>
                    </Badge>
                  ))}
                </div>
                <div className="flex gap-2">
                  <Input
                    value={newAvoid}
                    onChange={(e) => setNewAvoid(e.target.value)}
                    placeholder="Add to avoid list..."
                    onKeyDown={(e) => e.key === "Enter" && addAvoidItem()}
                  />
                  <Button variant="secondary" onClick={addAvoidItem}>
                    <Plus className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          </div>
        </TabsContent>

        <TabsContent value="workflows">
          <div className="max-w-3xl space-y-4 mt-6">
            {workflows.map((wf) => (
              <Card key={wf.name} className="cursor-pointer" onClick={() => setExpandedWf(expandedWf === wf.name ? null : wf.name)}>
                <CardContent className="p-4">
                  <div className="flex items-center justify-between">
                    <div>
                      <p className="text-sm font-medium">{wf.name}</p>
                      <p className="text-xs text-muted-foreground">
                        {(wf.manifest as Record<string, string>)?.description || "No description"}
                      </p>
                    </div>
                    <Badge variant="outline">{(wf.manifest as Record<string, string>)?.class_type_primary || "custom"}</Badge>
                  </div>
                  {expandedWf === wf.name && (
                    <pre className="mt-4 p-3 bg-secondary/30 rounded text-xs overflow-auto max-h-64 border border-border/50">
                      {JSON.stringify(wf.manifest, null, 2)}
                    </pre>
                  )}
                </CardContent>
              </Card>
            ))}
          </div>
        </TabsContent>
      </Tabs>
    </div>
  );
}
