from pathlib import Path
from collections import Counter
import json

def decode(path):
 data=Path(path).read_bytes();nl='\r\n' if b'\r\n' in data else '\n'
 # utf-8-sig only when a BOM is really there; it also decodes BOM-less UTF-8 and
 # Excel -> TXT would then add a BOM the original never had.
 for enc in (('utf-8-sig',) if data.startswith(b'\xef\xbb\xbf') else ())+('utf-8','cp949','euc-kr'):
  try:return data.decode(enc),enc,nl
  except UnicodeDecodeError:pass
 raise ValueError('지원 인코딩으로 TXT를 읽을 수 없습니다.')
def parse_txt(path):
 text,enc,nl=decode(path);headers=[];rows=[];meta={}
 for line in text.splitlines():
  if line.startswith('RowData:'):rows.append(line[8:].strip().split())
  else:
   headers.append(line)
   if ':' in line:
    k,v=line.split(':',1);meta[k.strip()]=v.strip()
 if not {'ROWCT','COLCT'}<=meta.keys():raise ValueError('ROWCT/COLCT가 없습니다.')
 rc,cc=int(meta['ROWCT']),int(meta['COLCT'])
 if len(rows)!=rc:raise ValueError(f'RowData 행 오류: {len(rows)}/{rc}')
 bad=[i+1 for i,r in enumerate(rows) if len(r)!=cc]
 if bad:raise ValueError(f'열 수 오류 Row: {bad[:8]}')
 return {'headers':headers,'rows':rows,'meta':meta,'encoding':enc,'newline':nl,'row_count':rc,'col_count':cc}
def discover(root,suffixes,skip_generated=True):
 root=Path(root);out=[]
 # TXT mode skips TXT made by Excel -> TXT; Excel mode must keep *_Map_Edit.xlsx, which is
 # exactly what users edit and convert back. '~$' files are Excel's lock files.
 generated=('_Converted',) if '.txt' in suffixes else ()
 for p in root.rglob('*'):
  if not p.is_file() or p.suffix.lower() not in suffixes or p.name.startswith('~$'):continue
  if skip_generated and any(x in p.stem for x in generated):continue
  out.append(p)
 return sorted(out,key=lambda p:str(p).lower())

def _load_heavy():
 from openpyxl import Workbook,load_workbook
 from openpyxl.styles import PatternFill,Font,Border,Side,Alignment
 from openpyxl.utils import get_column_letter
 return Workbook,load_workbook,PatternFill,Font,Border,Side,Alignment,get_column_letter
COLORS={'___':'FFFFFF','000':'DDF3DF','003':'D62728','007':'D08C00','014':'E53935','022':'7B1FA2','031':'1565C0','090':'666666'}
MEAN={'000':'Accept / Good','003':'Metal Residue','007':'Irregular Bump','014':'RDL Defect','022':'Scratch','031':'Foreign Material','090':'Customer Map Reject Die','___':'Outside Wafer'}
MEAN_KO={'000':'양품','003':'금속 잔류물','007':'범프 불량','014':'RDL 불량','022':'스크래치','031':'이물','090':'고객 맵 Reject Die','___':'웨이퍼 외곽 (Die 없음)'}
COLOR_NAME={'FFFFFF':'흰색','DDF3DF':'연두색','D62728':'빨강','D08C00':'주황','E53935':'선홍','7B1FA2':'보라','1565C0':'파랑','666666':'회색','F4B183':'살구색'}
UNKNOWN_COLOR='F4B183'
IMAGE_KINDS=[('code','BinCode_Map','Bin Code Map'),('meaning','BinMeaning_Map','Bin Meaning Map')]
def image_base(out):
 # Output path without its extension. Not with_suffix(''): 'LOT.01_Map_Edit.xlsx' must keep 'LOT.01'.
 out=Path(out);return out.with_name(out.name[:-len(out.suffix)] if out.suffix else out.name)
def image_paths(base):
 return [(label,base.with_name(base.name+'_'+suf+'.png')) for _,suf,label in IMAGE_KINDS]
def _font_color(fill):
 r,g,b=(int(fill[i:i+2],16) for i in (0,2,4));return 'FFFFFF' if (r*299+g*587+b*114)/1000<140 else '000000'
def _cell_style(code,cache,PatternFill,Font,Border,Side,Alignment):
 # One shared style set per code; the legend uses the same objects, so a copied
 # legend cell pastes exactly like a map die (value, fill and font).
 if code not in cache:
  fill=COLORS.get(code,UNKNOWN_COLOR);thin=Side(style='thin',color='B7B7B7')
  cache[code]=(PatternFill('solid',fgColor=fill),Border(left=thin,right=thin,top=thin,bottom=thin),Alignment(horizontal='center',vertical='center'),Font(size=7,color=_font_color(fill)))
 return cache[code]
def _apply(cell,code,cache,styles):
 fill,border,align,font=_cell_style(code,cache,*styles);cell.value=code;cell.fill=fill;cell.border=border;cell.alignment=align;cell.font=font;cell.number_format='@'
def write_legend(ws,rows,rc,cc,cache,styles,get_column_letter):
 """Bin Code legend to the right of the map (one blank column gap)."""
 PatternFill,Font,Border,Side,Alignment=styles;col=cc+3;L=lambda i:get_column_letter(col+i)
 present=sorted({x for r in rows for x in r});codes=[x for x in ['000','003','007','014','022','031','090','___'] if x in COLORS]+[x for x in present if x not in COLORS]
 first,last=f'$B$5',f'${get_column_letter(cc+1)}${4+rc}'
 head_fill=PatternFill('solid',fgColor='1F4E78');head_font=Font(bold=True,color='FFFFFF',size=9);thin=Side(style='thin',color='B7B7B7');box=Border(left=thin,right=thin,top=thin,bottom=thin)
 ws.cell(2,col,'Bin Code 범례 · 수정 가이드').font=Font(bold=True,size=12,color='1F4E78')
 for i,title in enumerate(['Bin Code','색상','Defect 종류','설명 (한글)','맵 수량','이 맵에 있음']):
  c=ws.cell(4,col+i,title);c.fill=head_fill;c.font=head_font;c.alignment=Alignment(horizontal='center',vertical='center');c.border=box
 for n,code in enumerate(codes):
  r=5+n;fill=COLORS.get(code,UNKNOWN_COLOR);_apply(ws.cell(r,col),code,cache,styles)
  info=[f'{COLOR_NAME.get(fill,"")} (#{fill})',MEAN.get(code,'Unknown Bin '+code),MEAN_KO.get(code,'미정의 Bin (색상 규칙 없음)'),f'=SUMPRODUCT(--({first}:{last}="{code}"))','●' if code in present else '']
  for i,v in enumerate(info,1):
   c=ws.cell(r,col+i,v);c.border=box;c.font=Font(size=9);c.alignment=Alignment(horizontal='center' if i in (4,5) else 'left',vertical='center')
  ws.cell(r,col+1).fill=PatternFill('solid',fgColor=fill)
  ws.cell(r,col+1).font=Font(size=9,color=_font_color(fill))
 r=5+len(codes);ws.cell(r,col+3,'Die 합계 (외곽 ___ 제외)').font=Font(bold=True,size=9);c=ws.cell(r,col+4,f'=SUMPRODUCT(--({first}:{last}<>"___"))');c.font=Font(bold=True,size=9);c.alignment=Alignment(horizontal='center')
 guide=['수정 방법',
  '1. 왼쪽 범례의 Bin Code 셀(색이 칠해진 셀)을 선택해 Ctrl+C 로 복사합니다.',
  '2. 맵에서 바꿀 die 셀(여러 셀 선택 가능)을 선택하고 Ctrl+V 로 붙여넣습니다. 코드와 색상이 함께 바뀝니다.',
  '3. 직접 입력할 때는 반드시 세 자리 코드(예: 003)로 입력하세요. 셀은 텍스트 형식이라 앞자리 0이 유지됩니다.',
  '4. ___ (웨이퍼 외곽) 셀은 die가 없는 위치이므로 바꾸지 마세요. 맵 크기(행/열)도 바꾸지 마세요.',
  '5. 맵 수량은 수정 즉시 다시 계산됩니다. 저장 후 프로그램에서 [Excel → TXT] 로 변환하면 수정된 TXT와 맵 이미지가 생성됩니다.',
  '* 범례에 없는 코드는 Unknown Bin(살구색)으로 표시되며 TXT에는 그대로 저장됩니다.']
 for i,text in enumerate(guide):
  c=ws.cell(r+2+i,col,text);c.font=Font(bold=(i==0),size=10 if i==0 else 9,color='1F4E78' if i==0 else '333333')
 for i,w in enumerate([10,16,24,24,10,11]):ws.column_dimensions[L(i)].width=w
 return codes
def txt_to_excel(src,out):
 Workbook,_,PatternFill,Font,Border,Side,Alignment,get_column_letter=_load_heavy();styles=(PatternFill,Font,Border,Side,Alignment);cache={}
 d=parse_txt(src);rows=d['rows'];rc=d['row_count'];cc=d['col_count'];wb=Workbook();ws=wb.active;ws.title='Map_Edit';ws.sheet_view.showGridLines=False;ws.freeze_panes='B5'
 ws.cell(1,2,f"{d['meta'].get('WAFER',Path(src).stem)} Map Edit ({cc} x {rc})");ws.cell(1,2).font=Font(bold=True,size=14,color='FFFFFF');ws.cell(1,2).fill=PatternFill('solid',fgColor='1F4E78');ws.merge_cells(start_row=1,start_column=2,end_row=1,end_column=cc+1)
 for c in range(cc):ws.cell(4,2+c,c);ws.column_dimensions[get_column_letter(2+c)].width=3.15
 for r,row in enumerate(rows):
  ws.cell(5+r,1,rc-1-r);ws.row_dimensions[5+r].height=17
  for c,code in enumerate(row):_apply(ws.cell(5+r,2+c),code,cache,styles)
 write_legend(ws,rows,rc,cc,cache,styles,get_column_letter)
 h=wb.create_sheet('Original_Header');h.append(['Line_No','Original_Header_Line'])
 for i,line in enumerate(d['headers'],1):h.append([i,line])
 m=wb.create_sheet('_Converter_Metadata');m['A1']=json.dumps({'row_count':rc,'col_count':cc,'start_row':5,'start_col':2,'source_encoding':d['encoding'],'source_newline':'CRLF' if d['newline']=='\r\n' else 'LF','valid_codes':sorted({x for r in rows for x in r})},ensure_ascii=False);m.sheet_state='veryHidden';wb.save(out)
 return {'output':str(out),'images':create_images(rows,d['meta'],image_base(out))}
def _code(v):
 # A die typed as 3 is stored by Excel as a number; restore the three-digit code.
 if isinstance(v,(int,float)) and not isinstance(v,bool) and float(v).is_integer():return f'{int(v):03d}'
 return str(v).strip()
def excel_to_txt(src,out):
 _,load_workbook,*_=_load_heavy();wb=load_workbook(src,data_only=False)
 if '_Converter_Metadata' in wb.sheetnames:
  md=json.loads(wb['_Converter_Metadata']['A1'].value);ws=wb['Map_Edit'];rc,cc=int(md['row_count']),int(md['col_count']);sr,sc=int(md.get('start_row',5)),int(md.get('start_col',2));headers=[str(wb['Original_Header'].cell(r,2).value) for r in range(2,wb['Original_Header'].max_row+1) if wb['Original_Header'].cell(r,2).value is not None];enc=md.get('source_encoding','utf-8');nl='\r\n' if md.get('source_newline')=='CRLF' else '\n'
 elif 'Map_수정' in wb.sheetnames and '원본_헤더' in wb.sheetnames:
  ws=wb['Map_수정'];h=wb['원본_헤더'];vals={str(h.cell(r,1).value):'' if h.cell(r,2).value is None else str(h.cell(r,2).value) for r in range(2,h.max_row+1) if h.cell(r,1).value is not None};rc,cc=int(vals['ROWCT']),int(vals['COLCT']);sr,sc=5,2;headers=[f'{k}:{v}' for k,v in vals.items()];enc='utf-8';nl='\r\n'
 else:raise ValueError('지원하는 변환 Excel 형식이 아닙니다.')
 rows=[]
 for r in range(rc):
  row=[]
  for c in range(cc):
   v=ws.cell(sr+r,sc+c).value
   if v is None or not str(v).strip():raise ValueError(f'빈 맵 셀: {ws.cell(sr+r,sc+c).coordinate}')
   row.append(_code(v))
  rows.append(row)
 Path(out).write_text(nl.join(headers+['RowData:'+' '.join(r) for r in rows])+nl,encoding=enc,newline='');meta={}
 for x in headers:
  if ':' in x:k,v=x.split(':',1);meta[k]=v
 return {'output':str(out),'images':create_images(rows,meta,image_base(out))}
def create_images(rows,meta,base):
 import numpy as np,matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 from matplotlib.colors import ListedColormap,BoundaryNorm
 from matplotlib.patches import Patch,Polygon
 rc,cc=len(rows),len(rows[0]);counts=Counter(x for r in rows for x in r);present=['000']+[x for x in sorted(counts) if x not in ('000','___')];codes=['___']+present;idx={x:i for i,x in enumerate(codes)};arr=np.zeros((rc,cc),int)
 for sr,row in enumerate(rows):
  for c,x in enumerate(row):arr[rc-1-sr,c]=idx[x]
 cmap=ListedColormap(['#'+COLORS.get(x,'F4B183') for x in codes]);norm=BoundaryNorm(np.arange(-.5,len(codes)+.5,1),cmap.N)
 for mode,suf in [('code','BinCode_Map'),('meaning','BinMeaning_Map')]:
  fig,ax=plt.subplots(figsize=(16,13),dpi=180);ax.imshow(arr,origin='lower',interpolation='none',cmap=cmap,norm=norm,extent=(-.5,cc-.5,-.5,rc-.5),aspect='equal');ax.set_xticks(np.arange(-.5,cc,1),minor=True);ax.set_yticks(np.arange(-.5,rc,1),minor=True);ax.grid(False,which='major');ax.grid(which='minor',color='#BCD0C0',linewidth=.35);ax.set_xticks(np.arange(0,cc,10));ax.set_yticks(np.arange(0,rc,10));ax.grid(False,which='major');ax.tick_params(which='minor',length=0);ax.set_xlim(-.5,cc-.5);ax.set_ylim(-2.8,rc-.5);ax.set_xlabel('Col (0-based, left to right)');ax.set_ylabel('Row (0-based, bottom to top)');ax.set_title(f"{meta.get('WAFER',base.name)}  {'Bin Code Map' if mode=='code' else 'Bin Meaning Map'} | Notch 6 o'clock",fontsize=22,pad=22);handles=[]
  for x in present:handles.append(Patch(facecolor='#'+COLORS.get(x,'F4B183'),edgecolor='black',label=(f'Bin {x}' if mode=='code' else MEAN.get(x,'Unknown Bin '+x))+f' ({counts[x]})'))
  ax.legend(handles=handles,loc='lower left',fontsize=11,frameon=True);cx=(cc-1)/2;ax.add_patch(Polygon([[cx-.7,-1.65],[cx+.7,-1.65],[cx,-.05]],closed=True,facecolor='white',edgecolor='#263238',clip_on=False));ax.text(cx,-2.15,"Notch 6'",ha='center',fontweight='bold');fig.savefig(base.with_name(base.name+'_'+suf+'.png'),bbox_inches='tight',facecolor='white');plt.close(fig)
 return [{'kind':label,'path':str(path)} for label,path in image_paths(base)]
