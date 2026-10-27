import { DownloadOutlined, PaperClipOutlined, UploadOutlined } from '@ant-design/icons'
import { Badge, Button, Drawer, Empty, Form, Input, List, Select, Tag, Tooltip, Upload } from 'antd'
import { useState } from 'react'

import { fmtDate, postJson, useAction, useDocuments, type DocEntity } from '../api'

const KINDS = [
  { value: 'CHARTER_PARTY', label: 'Charter party' },
  { value: 'ADDENDUM', label: 'Addendum / rider' },
  { value: 'BANK_GUARANTEE', label: 'Bank guarantee' },
  { value: 'QUOTE', label: 'Quotation' },
  { value: 'POLICY', label: 'Policy wording' },
  { value: 'INVOICE', label: 'Invoice / account' },
  { value: 'REPORT', label: 'Report' },
  { value: 'OTHER', label: 'Other' },
]
const KIND_LABEL = Object.fromEntries(KINDS.map((k) => [k.value, k.label]))
const ACCEPT = '.pdf,.doc,.docx,.xls,.xlsx,.png,.jpg,.jpeg,.txt,.msg,.eml'
const MAX_MB = 10

const readBase64 = (file: File) =>
  new Promise<string>((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] ?? '')
    reader.onerror = () => reject(new Error('The file could not be read.'))
    reader.readAsDataURL(file)
  })

const size = (bytes: number) => (bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`)

type Values = { kind: string; title: string; note?: string }

/**
 * A paperclip button that opens the documents kept against one record, with the newest version of each title
 * first. Uploading a title that exists adds a version; nothing is replaced.
 */
export default function Documents({ entity, entityKey, title, canUpload, count, defaultKind = 'OTHER' }: {
  entity: DocEntity
  entityKey: string
  title: string
  canUpload: boolean
  count?: number
  defaultKind?: string
}) {
  const [open, setOpen] = useState(false)
  const [file, setFile] = useState<File | null>(null)
  const [form] = Form.useForm<Values>()
  const docs = useDocuments(entity, entityKey, open)
  const upload = useAction(
    async (v: Values) =>
      postJson('/documents', { entity, entity_key: entityKey, kind: v.kind, title: v.title.trim(), note: v.note ?? '', filename: file!.name, content_base64: await readBase64(file!) }),
    'Document saved',
    () => {
      setFile(null)
      form.resetFields()
    },
  )
  const latest = (docs.data ?? []).filter((d) => d.latest)
  const older = (docs.data ?? []).filter((d) => !d.latest)

  return (
    <>
      <Tooltip title="Documents">
        <Badge count={count} size="small" color="#6b7280" offset={[-2, 2]}>
          <Button size="small" type="text" icon={<PaperClipOutlined />} onClick={() => setOpen(true)} aria-label={`Documents for ${title}`} />
        </Badge>
      </Tooltip>
      <Drawer open={open} onClose={() => setOpen(false)} title={`Documents · ${title}`} width={480} destroyOnHidden>
        <List
          loading={docs.isPending}
          dataSource={latest}
          locale={{ emptyText: <Empty image={Empty.PRESENTED_IMAGE_SIMPLE} description="Nothing filed yet" /> }}
          renderItem={(d) => {
            const versions = older.filter((o) => o.title === d.title)
            return (
              <List.Item
                actions={[
                  <Button key="get" size="small" icon={<DownloadOutlined />} href={`/api/documents/${d.id}/file`} aria-label={`Download ${d.title}`} />,
                ]}
              >
                <List.Item.Meta
                  title={
                    <>
                      {d.title} {d.version > 1 && <Tag>v{d.version}</Tag>}
                    </>
                  }
                  description={
                    <>
                      {KIND_LABEL[d.kind] ?? d.kind} · {d.filename} · {size(d.size)} · {fmtDate(d.at)} by {d.uploaded_by}
                      {d.note && <div>{d.note}</div>}
                      {versions.length > 0 && (
                        <div>
                          Earlier:{' '}
                          {versions.map((v) => (
                            <a key={v.id} href={`/api/documents/${v.id}/file`} style={{ marginRight: 8 }}>
                              v{v.version}
                            </a>
                          ))}
                        </div>
                      )}
                    </>
                  }
                />
              </List.Item>
            )
          }}
        />
        {canUpload && (
          <Form form={form} layout="vertical" requiredMark={false} initialValues={{ kind: defaultKind }} onFinish={upload.mutate} style={{ marginTop: 24 }}>
            <Form.Item label="File" required extra={`PDF, Word, Excel, image or email, up to ${MAX_MB} MB.`}>
              <Upload
                accept={ACCEPT}
                maxCount={1}
                fileList={file ? [{ uid: '1', name: file.name, status: 'done' }] : []}
                beforeUpload={(f) => {
                  if (f.size > MAX_MB * 1024 * 1024) return Upload.LIST_IGNORE
                  setFile(f)
                  if (!form.getFieldValue('title')) form.setFieldValue('title', f.name.replace(/\.[^.]+$/, ''))
                  return false
                }}
                onRemove={() => setFile(null)}
              >
                <Button icon={<UploadOutlined />}>Choose file</Button>
              </Upload>
            </Form.Item>
            <Form.Item name="kind" label="Type">
              <Select options={KINDS} />
            </Form.Item>
            <Form.Item name="title" label="Title" rules={[{ required: true, min: 2 }]} extra="Same title as an existing document = a new version of it.">
              <Input />
            </Form.Item>
            <Form.Item name="note" label="Note">
              <Input maxLength={500} />
            </Form.Item>
            <Button type="primary" htmlType="submit" loading={upload.isPending} disabled={!file}>
              Save document
            </Button>
          </Form>
        )}
      </Drawer>
    </>
  )
}
