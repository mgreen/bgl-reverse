from bgl import BGLParser, BGLReader
import os
import util
import gls

class BGL2MDX(BGLParser):

    def __init__(self, reader: BGLReader, out_path:str):
        self.path=out_path
        self.fout=open(out_path+".txt","w",encoding="utf-8")
        self.flog=open(out_path+".log","w",encoding="utf-8")
        try:
            os.mkdir(out_path)
        except:
            pass
        BGLParser.__init__(self)
        return
    
    def handle_term(self, title:str,def_frag:list,alternatives:list,properties:dict):
        self.fout.write(title)
        self.fout.write('\n')
        self.fout.writelines(def_frag)
        self.fout.write('\n')
        self.fout.write('</>\n')
        return

    def handle_properties(self,properties:dict):
        f=open(self.path+".ifo","w",encoding="utf-8")
        f.writelines(["Title: ",properties[gls.P_TITLE],'\n'])
        f.writelines(["Description: ",properties[gls.P_DESCRIPTION],'\n'])
        f.writelines(["S_Charset: ",properties[gls.P_S_CHARSET], '\n'])
        f.writelines(["T_Charset: ",properties[gls.P_T_CHARSET], '\n'])
        f.close()
        return

    def handle_res(self, name:str,data:bytes):
        res_f=open(self.path+'/'+name,'wb')
        res_f.write(data)
        res_f.close()
        return

    def handle_error(self,err:Exception,title,definition,alternatives,properties):
        self.flog.writelines(['ERROR:',str(err),"\n",title,'\n',definition,'\n\n\n'])
        return
    
    def transform_a_href(self,href:str) -> str:
        return 'entry://'+href.split('://')[1]
    
    def transform_img_src(self,src:str) -> str:
        return '/'+src




