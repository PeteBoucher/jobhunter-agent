"use client";

import { useSession } from "next-auth/react";
import { useRef, useState } from "react";
import { uploadCV } from "@/lib/api";

export default function CVUploadPage() {
  const { data: session } = useSession();
  const token = (session as any)?.apiToken as string | undefined;
  const fileRef = useRef<HTMLInputElement>(null);
  const [preview, setPreview] = useState("");
  const [fileName, setFileName] = useState("");
  const [uploading, setUploading] = useState(false);
  const [result, setResult] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  function handleFile(file: File) {
    setFileName(file.name);
    setResult(null);
    setError(null);
    const reader = new FileReader();
    reader.onload = (e) => setPreview((e.target?.result as string) ?? "");
    reader.readAsText(file);
  }

  function onDrop(e: React.DragEvent) {
    e.preventDefault();
    const file = e.dataTransfer.files[0];
    if (file) handleFile(file);
  }

  async function upload() {
    const file = fileRef.current?.files?.[0];
    if (!file || !token) return;
    setUploading(true);
    setError(null);
    try {
      const user = await uploadCV(token, file);
      setResult(`CV uploaded! Found ${user.skills.length} skills. Re-scoring in background…`);
    } catch (err: any) {
      setError(err.message ?? "Upload failed");
    } finally {
      setUploading(false);
    }
  }

  return (
    <div className="mx-auto max-w-2xl px-4 py-8">
      <h1 className="mb-2 text-2xl font-bold text-gray-900">Upload CV</h1>
      <p className="mb-6 text-sm text-gray-500">
        Upload a plain text or Markdown CV. Skills and preferences will be
        auto-extracted and your job scores will be recalculated in the background.
      </p>

      {/* Drop zone */}
      <div
        className="cursor-pointer rounded-xl border-2 border-dashed border-gray-300 p-8 text-center hover:border-blue-400 transition-colors"
        onDrop={onDrop}
        onDragOver={(e) => e.preventDefault()}
        onClick={() => fileRef.current?.click()}
      >
        <p className="text-sm text-gray-500">
          {fileName ? fileName : "Drag & drop a .txt or .md file, or click to browse"}
        </p>
        <input
          ref={fileRef}
          type="file"
          accept=".txt,.md,text/plain,text/markdown"
          className="hidden"
          onChange={(e) => {
            const f = e.target.files?.[0];
            if (f) handleFile(f);
          }}
        />
      </div>

      {/* Preview */}
      {preview && (
        <div className="mt-4 max-h-64 overflow-y-auto rounded-lg bg-gray-50 p-4 font-mono text-xs text-gray-600">
          {preview.slice(0, 2000)}
          {preview.length > 2000 && "…"}
        </div>
      )}

      {/* Upload button */}
      {fileName && (
        <button
          onClick={upload}
          disabled={uploading || !token}
          className="mt-4 rounded-lg bg-blue-600 px-6 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:opacity-50"
        >
          {uploading ? "Uploading…" : "Upload & re-score"}
        </button>
      )}

      {result && (
        <div className="mt-4 rounded-lg bg-green-50 p-4 text-sm text-green-700">{result}</div>
      )}
      {error && (
        <div className="mt-4 rounded-lg bg-red-50 p-4 text-sm text-red-600">{error}</div>
      )}
    </div>
  );
}
