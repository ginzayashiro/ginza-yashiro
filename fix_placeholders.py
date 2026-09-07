#!/usr/bin/env python3
"""写真待ちプレースホルダの埋め込み（写真集以外）"""
import re, os, shutil, subprocess

base = '/home/user/site_build'
os.chdir(base)
print('cwd:', os.getcwd())

with open('templates/index.html', encoding='utf-8') as f:
    html = f.read()

changes = []

# 1) PH-02 開栓シーン → 乾杯画像
old_ph = '<div class="photo-slot tall" data-photo="opening-scene" role="img" aria-label="開栓シーン（写真準備中）">'
new_ph = '<div class="photo-slot tall has-photo" data-photo="opening-scene" role="img" aria-label="開栓シーン" style="background-image:url(\'/static/img/remote/10_kanpai_cristal_7nin.jpg\');background-size:cover;background-position:center;">'
if old_ph in html:
    html = html.replace(old_ph, new_ph)
    changes.append('PH-02 開栓シーン → 乾杯画像')

# 2) スタッフ枠3つを実画像
for idx, num in enumerate(['1','2','3'], start=1):
    label = 'スタッフ' + (' A',' B',' C')[idx-1]
    old = (
        f'        <div class="photo-slot staff-photo" data-photo="staff-{num}" role="img" aria-label="スタッフ{idx}（近日公開）">\n'
        f'          <div class="photo-slot-label">スタッフ {idx}<br><small>近日公開</small></div>\n'
        f'        </div>\n'
        f'        <p class="staff-name">近日公開</p>'
    )
    new = (
        f'        <div class="photo-slot staff-photo has-photo" data-photo="staff-{num}" role="img" aria-label="{label}" style="background-image:url(\'/static/img/staff-{num}.jpg\');background-size:cover;background-position:center;"></div>\n'
        f'        <p class="staff-name">{label}</p>'
    )
    if old in html:
        html = html.replace(old, new)
        changes.append(f'staff-{num} → スタッフ {chr(64+idx)}')

html = html.replace(
    '※ スタッフのご紹介は順次公開いたします。',
    '※ ママとスタッフ一同、皆様のお越しをお待ちしております。'
)

with open('templates/index.html', 'w', encoding='utf-8') as f:
    f.write(html)

print('=== 変更 ===')
for c in changes:
    print(' -', c)

print()
print('=== 写真待ち残存箇所（order.html内・写真集用 else分岐のみ） ===')
subprocess.run(['grep','-rn','写真待ち|coming-soon|近日公開','templates/','static/'])
