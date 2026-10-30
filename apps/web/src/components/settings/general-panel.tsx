"use client";

import { useState, type FormEvent } from "react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { FieldHint, Input, Label, Textarea } from "@/components/ui/input";
import { useUpdateProject } from "@/lib/queries";
import type { Project } from "@/lib/types";

export function GeneralPanel({ project, editable }: { project: Project; editable: boolean }) {
  const update = useUpdateProject(project.slug);
  const [name, setName] = useState(project.name);
  const [description, setDescription] = useState(project.description);

  async function submit(event: FormEvent) {
    event.preventDefault();
    try {
      await update.mutateAsync({ name, description });
      toast.success("Project updated");
    } catch (error) {
      toast.error((error as Error).message);
    }
  }

  return (
    <Card>
      <CardContent className="pt-5">
        <form onSubmit={submit} className="max-w-xl space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="settings-name">Name</Label>
            <Input
              id="settings-name"
              value={name}
              onChange={(e) => setName(e.target.value)}
              disabled={!editable}
              required
            />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="settings-description">Description</Label>
            <Textarea
              id="settings-description"
              value={description}
              onChange={(e) => setDescription(e.target.value)}
              disabled={!editable}
            />
          </div>
          <div className="space-y-1.5">
            <p className="text-[13px] font-medium">Address</p>
            <FieldHint>
              The API serves this project under{" "}
              <code className="font-mono">/api/v1/projects/{project.slug}</code>; the id{" "}
              <code className="font-mono">{project.id}</code> works too.
            </FieldHint>
          </div>
          {editable ? (
            <Button type="submit" disabled={update.isPending || !name.trim()}>
              Save changes
            </Button>
          ) : (
            <FieldHint>Only owners can change project settings.</FieldHint>
          )}
        </form>
      </CardContent>
    </Card>
  );
}
