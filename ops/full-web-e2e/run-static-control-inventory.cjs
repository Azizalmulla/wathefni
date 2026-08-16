/**
 * Static JSX/TSX control inventory for HR dashboard + employee mobile.
 * Uses the repository TypeScript parser and emits machine-readable evidence.
 */
const fs = require('fs')
const os = require('os')
const path = require('path')

const ROOT = path.resolve(__dirname, '..', '..')
const ts = require(path.join(ROOT, 'apps', 'wathefni-dashboard', 'node_modules', 'typescript'))
const EVID = process.env.INTERACTION_AUDIT_EVID || path.join(os.tmpdir(), 'wathefni-control-smoke')

const TARGETS = [
  { app: 'dashboard', root: path.join(ROOT, 'apps/wathefni-dashboard/src') },
  { app: 'employee_mobile', root: path.join(ROOT, 'apps/wathefni-employee-mobile') },
]

const INTERACTIVE_TAGS = new Set([
  'button', 'a', 'input', 'select', 'textarea', 'summary', 'form',
  'Button', 'IconButton', 'Link', 'NavLink', 'Pressable', 'TouchableOpacity',
  'TouchableHighlight', 'Switch', 'TextInput', 'Picker', 'Tabs.Screen',
])

function walkFiles(root) {
  const out = []
  for (const entry of fs.readdirSync(root, { withFileTypes: true })) {
    if (['node_modules', 'dist', '.expo', '.git', 'coverage'].includes(entry.name)) continue
    const full = path.join(root, entry.name)
    if (entry.isDirectory()) out.push(...walkFiles(full))
    else if (/\.(tsx?|jsx?)$/.test(entry.name) && !/\.(test|spec)\.(tsx?|jsx?)$/.test(entry.name)) out.push(full)
  }
  return out
}

function tagName(node) {
  return node.tagName?.getText() || ''
}

function attrMap(node) {
  const attrs = {}
  for (const prop of node.attributes?.properties || []) {
    if (ts.isJsxSpreadAttribute(prop)) {
      attrs['...spread'] = prop.expression.getText()
      continue
    }
    if (!ts.isJsxAttribute(prop)) continue
    const key = prop.name.getText()
    if (!prop.initializer) attrs[key] = 'true'
    else if (ts.isStringLiteral(prop.initializer)) attrs[key] = prop.initializer.text
    else if (ts.isJsxExpression(prop.initializer)) attrs[key] = prop.initializer.expression?.getText() || ''
  }
  return attrs
}

function textChildren(node) {
  if (!node.parent || !ts.isJsxElement(node.parent)) return ''
  return node.parent.children
    .map((child) => ts.isJsxText(child) ? child.text : '')
    .join(' ')
    .replace(/\s+/g, ' ')
    .trim()
    .slice(0, 180)
}

function ancestorFormSubmit(node) {
  let current = node.parent
  while (current) {
    if (ts.isJsxElement(current)) {
      const opening = current.openingElement
      if (tagName(opening) === 'form') {
        const attrs = attrMap(opening)
        return attrs.onSubmit || ''
      }
    }
    current = current.parent
  }
  return ''
}

function classifyExpected(tag, attrs) {
  if (tag === 'form') return 'Submit invokes form handler with pending/error/success feedback.'
  if (attrs.href || attrs.to) return 'Navigate to a valid reachable route/deep link.'
  if (attrs.onChange || attrs.onChangeText) return 'Update controlled value/filter and refresh dependent state.'
  if (attrs.onPress || attrs.onClick) return 'Invoke declared handler once with feedback and safe repeat-click behavior.'
  return 'Visible control has a real handler or valid route.'
}

const rows = []
for (const target of TARGETS) {
  for (const file of walkFiles(target.root)) {
    const sourceText = fs.readFileSync(file, 'utf8')
    const source = ts.createSourceFile(
      file,
      sourceText,
      ts.ScriptTarget.Latest,
      true,
      file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS,
    )
    const visit = (node) => {
      if (ts.isJsxOpeningElement(node) || ts.isJsxSelfClosingElement(node)) {
        const tag = tagName(node)
        const attrs = attrMap(node)
        const hasHandler = Boolean(
          attrs.onClick || attrs.onPress || attrs.onSubmit || attrs.onChange ||
          attrs.onChangeText || attrs.onValueChange || attrs.href || attrs.to ||
          attrs.action || attrs.onSelect || attrs.onOpenChange,
        )
        const interactive =
          INTERACTIVE_TAGS.has(tag) ||
          hasHandler ||
          attrs.role === 'button' ||
          attrs.role === 'link' ||
          attrs.role === 'tab' ||
          attrs.tabIndex !== undefined
        if (interactive) {
          const pos = source.getLineAndCharacterOfPosition(node.getStart())
          const implicitSubmit = ['button', 'Button'].includes(tag) &&
            (attrs.type === 'submit' || !attrs.type) &&
            ancestorFormSubmit(node)
          const nativeBehavior =
            (tag === 'Tabs.Screen' && attrs.name) ||
            tag === 'summary' ||
            Boolean(attrs['...spread'])
          const explanatoryDisabled = Boolean(attrs.disabled || attrs['aria-disabled'])
          const dead = !hasHandler && !implicitSubmit && !nativeBehavior && !explanatoryDisabled &&
            !['input', 'select', 'textarea', 'TextInput', 'Picker', 'Switch'].includes(tag)
          const label =
            attrs['aria-label'] || attrs.accessibilityLabel || attrs.label ||
            attrs.title || attrs.placeholder || textChildren(node) || '(dynamic/unnamed)'
          const handler =
            attrs.onClick || attrs.onPress || attrs.onSubmit || attrs.onChange ||
            attrs.onChangeText || attrs.onValueChange || attrs.onSelect ||
            attrs.onOpenChange || attrs.href || attrs.to || attrs.name ||
            (implicitSubmit ? `form:${implicitSubmit}` : '')
          rows.push({
            app: target.app,
            screen: path.relative(target.root, file).replace(/\.(tsx?|jsx?)$/, ''),
            control: label,
            control_type: tag,
            expected_behavior: classifyExpected(tag, attrs),
            actual_result: dead
              ? 'No handler, route, submit ancestor, or native navigation declaration found.'
              : `Static binding: ${String(handler).slice(0, 500)}`,
            status: dead ? 'dead' : 'unproven',
            severity: dead ? 'P1' : 'P3',
            exact_fix_location: `${path.relative(ROOT, file)}:${pos.line + 1}`,
            file: path.relative(ROOT, file),
            line: pos.line + 1,
            handlers: {
              onClick: attrs.onClick || '',
              onPress: attrs.onPress || '',
              onSubmit: attrs.onSubmit || implicitSubmit || '',
              onChange: attrs.onChange || attrs.onChangeText || attrs.onValueChange || '',
              href: attrs.href || attrs.to || '',
              disabled: attrs.disabled || attrs['aria-disabled'] || '',
            },
          })
        }
      }
      ts.forEachChild(node, visit)
    }
    visit(source)
  }
}

const dead = rows.filter((row) => row.status === 'dead')
const summary = {
  generated_at: new Date().toISOString(),
  controls: rows.length,
  dashboard: rows.filter((r) => r.app === 'dashboard').length,
  employee_mobile: rows.filter((r) => r.app === 'employee_mobile').length,
  dead_candidates: dead.length,
  dead_by_app: {
    dashboard: dead.filter((r) => r.app === 'dashboard').length,
    employee_mobile: dead.filter((r) => r.app === 'employee_mobile').length,
  },
}

fs.mkdirSync(path.join(EVID, 'static'), { recursive: true })
fs.writeFileSync(path.join(EVID, 'static', 'control-inventory.json'), JSON.stringify(rows, null, 2) + '\n')
fs.writeFileSync(path.join(EVID, 'static', 'dead-control-candidates.json'), JSON.stringify(dead, null, 2) + '\n')
fs.writeFileSync(path.join(EVID, 'static', 'control-inventory-summary.json'), JSON.stringify(summary, null, 2) + '\n')
console.log(JSON.stringify(summary))
if (dead.length > 0) process.exitCode = 1
