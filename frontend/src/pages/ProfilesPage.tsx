import { zodResolver } from "@hookform/resolvers/zod";
import { useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useFieldArray, useForm } from "react-hook-form";
import { z } from "zod";

import { api } from "@/api/client";
import { useOrgQuery } from "@/api/queries";
import type { PreviewResult, ReaderProfile } from "@/api/types";
import { useSession } from "@/auth/session";
import { Banner, Button, Empty, Field, Loading, Page } from "@/components/ui";
import {
  NORMALIZATION_OPS,
  draftFromStep,
  emptyStep,
  opLabel,
  stepFromDraft,
  type StepDraft,
} from "@/domain/normalization";
import { errorMessage } from "@/lib/errors";
import { CREDENTIAL_TYPE_LABEL } from "@/lib/labels";

const schema = z
  .object({
    name: z.string().trim().min(1, "Indique el nombre."),
    credential_type: z.enum(["RFID", "FINGERPRINT", "PIN", "FACIAL"]),
    min_length: z.coerce.number().int().min(0),
    max_length: z.coerce.number().int().min(1),
    is_active: z.boolean(),
    normalization: z.array(
      z.object({
        op: z.enum([
          "trim",
          "upper",
          "strip_leading_zeros",
          "regex_extract",
          "hex_to_dec",
          "dec_to_hex",
          "pad_left",
        ]),
        pattern: z.string(),
        length: z.coerce.number(),
        char: z.string(),
      }),
    ),
  })
  .superRefine((value, context) => {
    if (value.min_length > value.max_length) {
      context.addIssue({
        code: z.ZodIssueCode.custom,
        path: ["min_length"],
        message: "El mínimo no puede superar al máximo.",
      });
    }
    value.normalization.forEach((step, index) => {
      if (step.op === "regex_extract" && !step.pattern.trim()) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["normalization", index, "pattern"],
          message: "Indique la expresión.",
        });
      }
      if (step.op === "pad_left" && (!Number.isInteger(step.length) || step.length < 1)) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["normalization", index, "length"],
          message: "La longitud debe ser un entero positivo.",
        });
      }
      if (step.op === "pad_left" && step.char.length !== 1) {
        context.addIssue({
          code: z.ZodIssueCode.custom,
          path: ["normalization", index, "char"],
          message: "Use un solo carácter.",
        });
      }
    });
  });

type FormValues = z.infer<typeof schema>;

const emptyForm: FormValues = {
  name: "",
  credential_type: "RFID",
  min_length: 1,
  max_length: 128,
  is_active: true,
  normalization: [],
};

function fromProfile(profile: ReaderProfile): FormValues {
  return {
    name: profile.name,
    credential_type: profile.credential_type,
    min_length: profile.min_length,
    max_length: profile.max_length,
    is_active: profile.is_active,
    normalization: profile.normalization.map(draftFromStep),
  };
}

export function ProfilesPage({ canEdit }: { canEdit: boolean }) {
  const organizationId = useSession((state) => state.organizationId);
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [error, setError] = useState("");
  const [sample, setSample] = useState("  00ab12");
  const [preview, setPreview] = useState<PreviewResult | null>(null);
  const profiles = useOrgQuery(["/reader-profiles/"], () =>
    api.list<ReaderProfile>("/reader-profiles/", { page_size: 100, ordering: "name" }),
  );
  const form = useForm<FormValues>({
    resolver: zodResolver(schema),
    defaultValues: emptyForm,
  });
  const steps = useFieldArray({ control: form.control, name: "normalization" });
  const selected = profiles.data?.results.find((profile) => profile.id === selectedId) ?? null;

  useEffect(() => {
    if (selected && !creating) {
      form.reset(fromProfile(selected));
    }
  }, [selected, creating, form]);

  function startCreate() {
    setCreating(true);
    setSelectedId(null);
    setPreview(null);
    form.reset(emptyForm);
  }

  async function onSubmit(values: FormValues) {
    setError("");
    const body = {
      name: values.name,
      credential_type: values.credential_type,
      min_length: values.min_length,
      max_length: values.max_length,
      is_active: values.is_active,
      normalization: values.normalization.map((step) => stepFromDraft(step as StepDraft)),
    };
    try {
      const saved = selected
        ? await api.update<ReaderProfile>(`/reader-profiles/${selected.id}/`, body)
        : await api.create<ReaderProfile>("/reader-profiles/", body);
      setCreating(false);
      setSelectedId(saved.id);
      await queryClient.invalidateQueries({ queryKey: [organizationId, "/reader-profiles/"] });
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  async function runPreview() {
    const values = form.getValues();
    const targetId = selected?.id ?? profiles.data?.results[0]?.id;
    if (!targetId) {
      setPreview({ ok: false, error: "Guarde el perfil para probar la normalización." });
      return;
    }
    setError("");
    try {
      const result = await api.create<PreviewResult>(`/reader-profiles/${targetId}/preview/`, {
        sample,
        normalization: values.normalization.map((step) => stepFromDraft(step as StepDraft)),
        min_length: Number(values.min_length),
        max_length: Number(values.max_length),
      });
      setPreview(result);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }

  return (
    <Page
      title="Perfiles de lector"
      lede="La normalización convierte el texto del lector en el identificador que guarda la credencial."
      actions={
        canEdit ? (
          <Button type="button" onClick={startCreate}>
            Nuevo perfil
          </Button>
        ) : null
      }
    >
      {error ? <Banner>{error}</Banner> : null}
      {profiles.isLoading ? <Loading /> : null}
      <div className="split">
        <div className="table-wrap">
          <table className="grid">
            <caption className="sr-only">Perfiles</caption>
            <thead>
              <tr>
                <th>Nombre</th>
                <th>Tipo</th>
                <th>Pasos</th>
              </tr>
            </thead>
            <tbody>
              {profiles.data?.results.map((profile) => (
                <tr key={profile.id} className={profile.id === selectedId ? "selected" : ""}>
                  <td>
                    <button
                      type="button"
                      className="linkish"
                      onClick={() => {
                        setCreating(false);
                        setSelectedId(profile.id);
                        setPreview(null);
                      }}
                    >
                      {profile.name}
                    </button>
                  </td>
                  <td>{CREDENTIAL_TYPE_LABEL[profile.credential_type]}</td>
                  <td>{profile.normalization.length}</td>
                </tr>
              ))}
            </tbody>
          </table>
          {(profiles.data?.results.length ?? 0) === 0 && !profiles.isLoading ? (
            <Empty>No hay perfiles.</Empty>
          ) : null}
        </div>
        {creating || selected ? (
          <aside className="detail card">
            <h2>{selected && !creating ? selected.name : "Nuevo perfil"}</h2>
            <form className="form-grid" onSubmit={form.handleSubmit(onSubmit)}>
              <Field label="Nombre" error={form.formState.errors.name?.message}>
                <input {...form.register("name")} disabled={!canEdit} />
              </Field>
              <Field label="Tipo de credencial">
                <select {...form.register("credential_type")} disabled={!canEdit}>
                  {Object.entries(CREDENTIAL_TYPE_LABEL).map(([value, label]) => (
                    <option key={value} value={value}>
                      {label}
                    </option>
                  ))}
                </select>
              </Field>
              <Field label="Longitud mínima" error={form.formState.errors.min_length?.message}>
                <input type="number" {...form.register("min_length")} disabled={!canEdit} />
              </Field>
              <Field label="Longitud máxima" error={form.formState.errors.max_length?.message}>
                <input type="number" {...form.register("max_length")} disabled={!canEdit} />
              </Field>
              <label className="check">
                <input type="checkbox" {...form.register("is_active")} disabled={!canEdit} />
                Activo
              </label>
              <div className="steps">
                <h3>Pasos</h3>
                {steps.fields.map((field, index) => {
                  const op = form.watch(`normalization.${index}.op`);
                  return (
                    <div className="step" key={field.id}>
                      <strong>
                        {index + 1}. {opLabel(op)}
                      </strong>
                      {op === "regex_extract" ? (
                        <Field
                          label="Expresión"
                          error={form.formState.errors.normalization?.[index]?.pattern?.message}
                        >
                          <input
                            {...form.register(`normalization.${index}.pattern`)}
                            disabled={!canEdit}
                          />
                        </Field>
                      ) : null}
                      {op === "pad_left" ? (
                        <>
                          <Field
                            label="Longitud"
                            error={form.formState.errors.normalization?.[index]?.length?.message}
                          >
                            <input
                              type="number"
                              {...form.register(`normalization.${index}.length`)}
                              disabled={!canEdit}
                            />
                          </Field>
                          <Field
                            label="Carácter"
                            error={form.formState.errors.normalization?.[index]?.char?.message}
                          >
                            <input
                              maxLength={1}
                              {...form.register(`normalization.${index}.char`)}
                              disabled={!canEdit}
                            />
                          </Field>
                        </>
                      ) : null}
                      {canEdit ? (
                        <div className="row-actions">
                          <button
                            type="button"
                            onClick={() => steps.move(index, index - 1)}
                            disabled={index === 0}
                          >
                            Subir
                          </button>
                          <button
                            type="button"
                            onClick={() => steps.move(index, index + 1)}
                            disabled={index === steps.fields.length - 1}
                          >
                            Bajar
                          </button>
                          <button type="button" onClick={() => steps.remove(index)}>
                            Quitar
                          </button>
                        </div>
                      ) : null}
                    </div>
                  );
                })}
                {canEdit ? (
                  <Field label="Agregar paso">
                    <select
                      value=""
                      onChange={(event) => {
                        const op = event.target.value as StepDraft["op"];
                        if (op) {
                          steps.append(emptyStep(op));
                        }
                      }}
                    >
                      <option value="">Elegir operación</option>
                      {NORMALIZATION_OPS.map((item) => (
                        <option key={item.op} value={item.op}>
                          {item.label}
                        </option>
                      ))}
                    </select>
                  </Field>
                ) : null}
              </div>
              {canEdit ? (
                <Button type="submit" disabled={form.formState.isSubmitting}>
                  Guardar perfil
                </Button>
              ) : null}
            </form>
            <div className="preview">
              <Field label="Texto de ejemplo">
                <input value={sample} onChange={(event) => setSample(event.target.value)} />
              </Field>
              <Button type="button" variant="ghost" onClick={() => void runPreview()}>
                Vista previa
              </Button>
              {preview ? (
                <Banner tone={preview.ok ? "ok" : "error"}>
                  {preview.ok ? `Resultado: ${preview.payload}` : preview.error}
                </Banner>
              ) : null}
            </div>
          </aside>
        ) : (
          <aside className="detail card">
            <Empty>Seleccione un perfil.</Empty>
          </aside>
        )}
      </div>
    </Page>
  );
}
