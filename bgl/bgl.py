"""实现完整的BGL格式解析，其中部分数据意义不明"""

import io
import gzip

import util
import gls


from html.parser import HTMLParser

def unpack_block(data:memoryview,x:int)-> (memoryview,memoryview):
    """return a tuple (block_data,unprocessed)"""
    blk_len=util.unpack_ui(bytes(data[0:x]))
    return (data[x:x+blk_len],data[x+blk_len:])

def unpack_property(data:memoryview) -> (int,memoryview):
    return (util.unpack_ui(bytes(data[0:2])),data[2:])

def unpack_parameter(data:memoryview) -> (int,bytes):
    return (data[0],bytes(data[1:]))

def unpack_term_property(data:bytes) -> dict:
    """return dict(prop_id -> prop_value)"""
    # TPBLOCK FORMAT:
    # 1 Byte spec，如果高四位小于4，低四位为prop_id；否则 next 1 Byte为prop_id，数据长度为spec-0x3f，如果长度>=10，则之后为block(1)
    #
    prop={}
    while len(data)>1:
        spec=data[0]
        if spec<0x40:
            prop_id=0x0f&spec
            if (spec>>4)==0:
                prop_value=data[1]
                data=data[2:]
            else:
                (prop_value,data)=unpack_block(data[1:],1)
        else:
            prop_id=data[1] # next byte as prop id
            v_len=spec-0x3f
            if v_len>0x10:
                (prop_value,data)=unpack_block(data[2:],1)
            else:
                prop_value=data[2:2+v_len]
                data=data[2+v_len:]
        prop[prop_id]=prop_value
    return prop

def unpack_term(data:memoryview) -> (memoryview, memoryview, list, dict):
    """return (title,definition,alternatives,properties)"""
    (title,data)=unpack_block(data,1)
    (definition,data)=unpack_block(data,2)
    alternatives=[]
    while len(data)>0:
        (alt_i,data)=unpack_block(data,1)
        alternatives.append(alt_i)

    (definition,rawprop)=util.mem_split(definition,0x14)
    return (title,definition,alternatives,unpack_term_property(bytes(rawprop)))

def unpack_res(data:memoryview) -> (memoryview,memoryview):
    return unpack_block(data,1)

class BGLReader(gzip.GzipFile):
    def __init__(self,path:str):
        f=open(path,'rb')
        BGLReader._seek_to_gz_header(f)
        gzip.GzipFile.__init__(self,fileobj=f)
        self._eof=False
        self._next_rec=None
        return
    
    @staticmethod
    def _seek_to_gz_header(f):
        header=util.read_ui(f,4)
        if header==0x12340001:
            f.seek(0x69)
        elif header==0x12340002:
            f.seek(0x69)
        else:
            raise IOError("invald header: {0:#x}".format(header))
        return

    def _read_rec_data(self,pspec:int) -> memoryview:
        """read record data with high nibble of spec"""
        if pspec<4:
            rec_len=util.read_ui(self,pspec+1)
        else:
            rec_len=pspec-4

        return memoryview(self.read(rec_len))

    def _read_rec(self) -> (int,memoryview):
        spec=util.read_ui(self,1)
        if spec==None:
            return None
        
        rec_type=spec&0x0f
        rec_data=self._read_rec_data(spec>>4)
        
        return (rec_type,rec_data)
        
    
    def next_rec(self) -> (int,memoryview):
        """read next record from a BGLFile, return a tuple (rec_type,data), None if eof"""
        if self.eof():
            return None
        else:
            rec=self._next_rec
            self._next_rec=None
            return rec
    
    def eof(self) -> bool:
        if self._eof:
            return True
        elif self._next_rec != None :
            return False
        else:
            self._next_rec=self._read_rec()
            if self._next_rec==None:
                self._eof=True
                return True
            else:
                return False

    def reset(self):
        self.seek(0)



def parse_property(data:dict)->dict:
    prop={}
    
    prop[0x1a]=gls.CHARSET[util.unpack_ui(bytes(data[0x1a]))]
    prop[0x1b]=gls.CHARSET[util.unpack_ui(bytes(data[0x1b]))]

    for prop_id in [
        gls.P_TITLE,
        gls.P_AUTHOR_NAME,
        gls.P_AUTHOR_EMAIL
        ]:
        prop[prop_id]=bytes(data[prop_id]).decode('latin1')
    
    for prop_id in [
            gls.P_ICON,
            gls.P_MANUAL]:
        prop[prop_id]=data[prop_id]
    
    return prop


class GLSHTMLContentFilter(HTMLParser):
    
    def __init__(self,a_href,img_src):
        HTMLParser.__init__(self)
        self.parts=[]
        self.tags=[]
        self.transform_a_href=a_href
        self.transform_img_src=img_src

    def reset(self):
        HTMLParser.reset(self)
        self.parts=[]
        self.tags=[]
    
    def handle_entityref(self,name:str):
        self.parts.append('&'+name+';')

    def handle_charref(self,name):
        self.parts.append(str(util.parse_charref(name)))
    
    def handle_starttag(self,tag,attrs):
        attrs=dict(attrs)
        if tag=="font":
            color=attrs.get("color")
            if color!=None:
                self.parts.append("<font color='"+color+"'>")
                self.tags.append(tag)
            else:
                # color tag is useless
                # by pushing None, the close tag will be ignored
                self.tags.append(None)
        elif tag=="a":
            attrs["href"]=self.transform_a_href(attrs["href"])
            util.append_start_tag(self.parts,tag,attrs)
            self.tags.append(tag)
        elif tag=="br":
            self.parts.append("<br/>")
        elif tag=="img":
            attrs["src"]=self.transform_img_src(attrs["src"])
            util.append_start_tag(self.parts,tag,attrs)
            self.tags.append(tag)
        elif tag=="charset":
            self.tags.append("charset")
        else:
            # default action
            util.append_start_tag(self.parts,tag,attrs)
            self.tags.append(tag)
        return

    def handle_startendtag(self,tag,attrs):
        util.append_startend_tag(self.parts,tag,attrs)
        return
    
    def handle_endtag(self,tag):
        if len(self.tags)==0:
            return
        elif self.tags[-1]==None and tag=='font': # eliminate font tag with only face attribute
            self.tags.pop()
        elif self.tags[-1]!=tag: # if tag is invalid, ignore it
            return
        elif self.tags[-1]=='charset':
            self.tags.pop()
            return
        else:
            self.tags.pop()
            util.append_end_tag(self.parts,tag)
        return

    def handle_data(self,data):
        if len(self.tags)==0:
            self.parts.append(data)
            return
        lasttag=self.tags[-1];
        if lasttag=="charset":
            self.parts.append(chr(int(data[0:4],16)))
        else:
            self.parts.append(data)
        return

class BGLParser:
    def __init__(self):
        return

    def _read_properties(self,reader:BGLReader):
        parameters_r={}
        properties_r={}
        
        while True:
            rec=reader.next_rec()
            if rec[0]==gls.DELIMITER:
                
                break
            elif rec[0]==gls.PARAMETER:
                (k,v)=unpack_parameter(rec[1])
                parameters_r[k]=v
            elif rec[0]==gls.PROPERTY:
                (k,v)=unpack_property(rec[1])
                properties_r[k]=v
        
        self.properties={
            gls.P_S_CHARSET:   gls.CHARSET[ bytes(properties_r[gls.P_S_CHARSET])[0] ],
            gls.P_T_CHARSET:   gls.CHARSET[ bytes(properties_r[gls.P_T_CHARSET])[0] ],
            gls.P_TITLE:       bytes(properties_r[gls.P_TITLE]).decode('latin1'),
            gls.P_DESCRIPTION: bytes(properties_r[gls.P_DESCRIPTION]).decode('latin1')
        }
        self.handle_properties()
        return

    def _parse_term_properties(self,prop:dict) -> dict:
        
        return {}
    
    def parse(self,reader:BGLReader,reset:bool=True):
        if reset:
            reader.reset()
        self.reader=reader
        
        self._read_properties(reader)
        
        charset_s=self.properties[gls.P_S_CHARSET]
        charset_t=self.properties[gls.P_T_CHARSET]
        
        while not reader.eof():
            rec=reader.next_rec()
            
            if rec[0] == gls.TERM_A or rec[0] == gls.TERM_1:
                (title_r,definition_r,alternatives_r,properties_r)=unpack_term(rec[1])
                title=util.decode(bytes(title_r),charset_s)
                
                definition=util.decode(bytes(alt), charset_s)
                
                alternatives=[]
                for alt in alternatives_r:
                    alternatives.append( util.decode(bytes(alt), charset_s) )
                definition=util.decode(bytes(definition_r),charset_t)
                
                properties=self._parse_term_properties(properties_r)
                
                self.handle_term(title, definition, alternatives, properties)
                
            elif rec[0] == gls.RESOURCE:
                (name_r,data)=unpack_res(rec[1])
                self.handle_res( bytes(name_r).decode('latin1'), bytes(data) )
                
            elif rec[0] ==  gls.TERM_B:
                raise Exception("TERM_B not implemented")
        
        self.reader.close()
        self.handle_parse_complete()
        return

    def handle_term(self, title:str,definition:str,alternatives:list,properties:dict):
        pass
    
    def handle_res(self, name:str,data:bytes):
        pass
    
    def handle_properties(self,properties:dict):
        pass
    
    def handle_parse_complete(self):
        pass

