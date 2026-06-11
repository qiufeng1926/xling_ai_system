<template>
  <div class="page-card">
    <div class="filter-bar">
      <el-select v-model="filterCategory" placeholder="分类" clearable style="width: 140px" @change="loadData">
        <el-option v-for="(label, key) in categories" :key="key" :label="label" :value="key" />
      </el-select>
      <el-button type="primary" @click="openCreate">新建标签</el-button>
      <el-button @click="loadData">刷新</el-button>
    </div>

    <el-table v-loading="loading" :data="list" stripe row-key="id" default-expand-all>
      <el-table-column prop="name" label="标签名称" min-width="180" />
      <el-table-column label="分类" width="120">
        <template #default="{ row }">
          <el-tag :type="categoryTagType(row.category) as any" size="small">
            {{ formatTagCategory(row.category) }}
          </el-tag>
        </template>
      </el-table-column>
      <el-table-column prop="level" label="层级" width="80" />
      <el-table-column prop="influencer_count" label="关联达人数" width="110" />
      <el-table-column label="操作" width="160" fixed="right">
        <template #default="{ row }">
          <el-button link type="primary" @click="openEdit(row)">编辑</el-button>
          <el-button link type="danger" @click="handleDelete(row)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <el-dialog v-model="showDialog" :title="editing ? '编辑标签' : '新建标签'" width="460px">
      <el-form :model="form" label-width="80px">
        <el-form-item label="名称" required>
          <el-input v-model="form.name" placeholder="标签名称" />
        </el-form-item>
        <el-form-item label="分类">
          <el-select v-model="form.category" style="width: 100%">
            <el-option v-for="(label, key) in categories" :key="key" :label="label" :value="key" />
          </el-select>
        </el-form-item>
        <el-form-item label="父标签">
          <el-select v-model="form.parent_id" clearable placeholder="无（顶级标签）" style="width: 100%">
            <el-option
              v-for="t in flatTags.filter((x) => x.id !== editing?.id)"
              :key="t.id"
              :label="t.name"
              :value="t.id"
            />
          </el-select>
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="showDialog = false">取消</el-button>
        <el-button type="primary" :loading="saving" @click="handleSave">保存</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import {
  TAG_CATEGORY_MAP,
  categoryTagType,
  createTag,
  deleteTag,
  formatTagCategory,
  getTagCategories,
  getTags,
  updateTag,
  type Tag,
} from '@/api/tags'

const loading = ref(false)
const saving = ref(false)
const showDialog = ref(false)
const filterCategory = ref('')
const list = ref<Tag[]>([])
const flatTags = ref<Tag[]>([])
const categories = ref<Record<string, string>>({ ...TAG_CATEGORY_MAP })
const editing = ref<Tag | null>(null)

const form = reactive({
  name: '',
  category: 'content',
  parent_id: undefined as number | undefined,
})

function flattenTags(tags: Tag[]): Tag[] {
  const result: Tag[] = []
  for (const tag of tags) {
    result.push(tag)
    if (tag.children?.length) {
      result.push(...flattenTags(tag.children))
    }
  }
  return result
}

async function loadData() {
  loading.value = true
  try {
    const res = await getTags({ category: filterCategory.value || undefined, tree: true })
    list.value = res.data
    flatTags.value = flattenTags(res.data)
  } finally {
    loading.value = false
  }
}

function resetForm() {
  form.name = ''
  form.category = 'content'
  form.parent_id = undefined
  editing.value = null
}

function openCreate() {
  resetForm()
  showDialog.value = true
}

function openEdit(row: Tag) {
  editing.value = row
  form.name = row.name
  form.category = row.category || 'content'
  form.parent_id = row.parent_id || undefined
  showDialog.value = true
}

async function handleSave() {
  if (!form.name.trim()) {
    ElMessage.warning('请输入标签名称')
    return
  }
  saving.value = true
  try {
    const payload = {
      name: form.name.trim(),
      category: form.category,
      parent_id: form.parent_id ?? null,
    }
    if (editing.value) {
      await updateTag(editing.value.id, payload)
      ElMessage.success('更新成功')
    } else {
      await createTag(payload)
      ElMessage.success('创建成功')
    }
    showDialog.value = false
    loadData()
  } finally {
    saving.value = false
  }
}

async function handleDelete(row: Tag) {
  await ElMessageBox.confirm(`确认删除标签「${row.name}」？`, '提示', { type: 'warning' })
  await deleteTag(row.id)
  ElMessage.success('删除成功')
  loadData()
}

onMounted(async () => {
  try {
    const res = await getTagCategories()
    categories.value = res.data
  } catch {
    /* use default map */
  }
  loadData()
})
</script>
