from pathlib import Path
from collections import Counter
import json

def decode(path):
 data=Path(path).read_bytes();nl='\r\n' if b'\r\n' in data else '\n'
 for enc in ('utf-8-sig','utf-8','cp949','euc-kr'):
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
 for p in root.rglob('*'):
  if not p.is_file() or p.suffix.lower() not in suffixes:continue
  if skip_generated and any(x in p.stem for x in ('_Map_Edit','_Converted','_BinCode_Map','_BinMeaning_Map')):continue
  out.append(p)
 return sorted(out,key=lambda p:str(p).lower())

def _load_heavy():
 from openpyxl import Workbook,load_workbook
 from openpyxl.styles import PatternFill,Font,Border,Side,Alignment
 from openpyxl.utils import get_column_letter
 return Workbook,load_workbook,PatternFill,Font,Border,Side,Alignment,get_column_letter
COLORS={'___':'FFFFFF','000':'DDF3DF','003':'D62728','007':'D08C00','014':'E53935','022':'7B1FA2','031':'1565C0','090':'666666'}
MEAN={'000':'Accept / Good','003':'Metal Residue','007':'Irregular Bump','014':'RDL Defect','022':'Scratch','031':'Foreign Material','090':'Customer Map Reject Die','___':'Outside Wafer'}
def txt_to_excel(src,out):
 Workbook,_,PatternFill,Font,Border,Side,Alignment,get_column_letter=_load_heavy();d=parse_txt(src);rows=d['rows'];rc=d['row_count'];cc=d['col_count'];wb=Workbook();ws=wb.active;ws.title='Map_Edit';ws.sheet_view.showGridLines=False;ws.freeze_panes='B5';thin=Side(style='thin',color='B7B7B7');bd=Border(left=thin,right=thin,top=thin,bottom=thin)
 ws=ws
 ws.cell(1,2,f"{d['meta'].get('WAFER',Path(src).stem)} Map Edit ({cc} x {rc})");ws.cell(1,2).font=Font(bold=True,size=14,color='FFFFFF');ws.cell(1,2).fill=PatternFill('solid',fgColor='1F4E78');ws.merge_cells(start_row=1,start_column=2,end_row=1,end_column=cc+1)
 for c in range(cc):ws.cell(4,2+c,c);ws.column_dimensions[get_column_letter(2+c)].width=3.15
 for r,row in enumerate(rows):
  ws.cell(5+r,1,rc-1-r);ws.row_dimensions[5+r].height=17
  for c,code in enumerate(row):
   cell=ws.cell(5+r,2+c,code);cell.fill=PatternFill('solid',fgColor=COLORS.get(code,'F4B183'));cell.border=bd;cell.alignment=Alignment(horizontal='center');cell.font=Font(size=7,color='000000')
 h=wb.create_sheet('Original_Header');h.append(['Line_No','Original_Header_Line'])
 for i,line in enumerate(d['headers'],1):h.append([i,line])
 m=wb.create_sheet('_Converter_Metadata');m['A1']=json.dumps({'row_count':rc,'col_count':cc,'start_row':5,'start_col':2,'source_encoding':d['encoding'],'source_newline':'CRLF' if d['newline']=='\r\n' else 'LF','valid_codes':sorted({x for r in rows for x in r})},ensure_ascii=False);m.sheet_state='veryHidden';wb.save(out);create_images(rows,d['meta'],Path(out).with_suffix(''))
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
   row.append(str(v).strip())
  rows.append(row)
 Path(out).write_text(nl.join(headers+['RowData:'+' '.join(r) for r in rows])+nl,encoding=enc,newline='');meta={}
 for x in headers:
  if ':' in x:k,v=x.split(':',1);meta[k]=v
 create_images(rows,meta,Path(out).with_suffix(''))
def create_images(rows,meta,base):
 import numpy as np,matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
 from matplotlib.colors import ListedColormap,BoundaryNorm
 from matplotlib.patches import Patch,Polygon
 rc,cc=len(rows),len(rows[0]);counts=Counter(x for r in rows for x in r);present=['000']+[x for x in sorted(counts) if x not in ('000','___')];codes=['___']+present;idx={x:i for i,x in enumerate(codes)};arr=np.zeros((rc,cc),int)
 for sr,row in enumerate(rows):
  for c,x in enumerate(row):arr[rc-1-sr,c]=idx[x]
 cmap=ListedColormap(['#'+COLORS.get(x,'F4B183') for x in codes]);norm=BoundaryNorm(np.arange(-.5,len(codes)+.5,1),cmap.N)
 for mode,suf in [('code','BinCode_Map'),('meaning','BinMeaning_Map')]:
  fig,ax=plt.subplots(figsize=(16,13),dpi=180);ax.imshow(arr,origin='lower',interpolation='none',cmap=cmap,norm=norm,extent=(-.5,cc-.5,-.5,rc-.5),aspect='equal');ax.set_xticks(np.arange(-.5,cc,1),minor=True);ax.set_yticks(np.arange(-.5,rc,1),minor=True);ax.grid(False,which='major');ax.grid(which='minor',color='#BCD0C0',linewidth=.35);ax.set_xticks(np.arange(0,cc,10));ax.set_yticks(np.arange(0,rc,10));ax.grid(False,which='major');ax.tick_params(which='minor',length=0);ax.set_xlim(-.5,cc-.5);ax.set_ylim(-2.8,rc-.5);ax.set_xlabel('Col (0-based, left to right)');ax.set_ylabel('Row (0-based, bottom to top)');ax.set_title(f"{meta.get('WAFER',base.stem)}  {'Bin Code Map' if mode=='code' else 'Bin Meaning Map'} | Notch 6 o'clock",fontsize=22,pad=22);handles=[]
  for x in present:handles.append(Patch(facecolor='#'+COLORS.get(x,'F4B183'),edgecolor='black',label=(f'Bin {x}' if mode=='code' else MEAN.get(x,'Unknown Bin '+x))+f' ({counts[x]})'))
  ax.legend(handles=handles,loc='lower left',fontsize=11,frameon=True);cx=(cc-1)/2;ax.add_patch(Polygon([[cx-.7,-1.65],[cx+.7,-1.65],[cx,-.05]],closed=True,facecolor='white',edgecolor='#263238',clip_on=False));ax.text(cx,-2.15,"Notch 6'",ha='center',fontweight='bold');fig.savefig(base.with_name(base.stem+'_'+suf+'.png'),bbox_inches='tight',facecolor='white');plt.close(fig)
