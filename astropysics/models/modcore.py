#Copyright (c) 2008 Erik Tollerud (etolleru@uci.edu) 

from __future__ import division,with_statement
from ..constants import pi
import numpy as np
try:
    #requires Python 2.6
    from abc import ABCMeta
    from abc import abstractmethod
    from abc import abstractproperty
except ImportError: #support for earlier versions
    abstractmethod = lambda x:x
    abstractproperty = property
    ABCMeta = type

class ModelTypeError(Exception):
    """
    This exception indicates a problem with the value of the input 
    or output of a model 
    """
    def __init__(self,message):
        super(ModelTypeError,self).__init__(message)
    
class ParametricModel(object):
    """
    The superclass of all models with parameters
    
    subclasses should implement abstract properties and methods:
    * __call__: Takes a single argument as the model input, returns the
                model output
    
    * params: a sequence of names for the parameters of the model
    * parvals: a sequence of values for the parameters of the model
    
    optional overrides:
    * pardict: a dictionary with keys as parameter names and values as 
      the value for that parameter
    * inv: compute the inverse of the model
    """
    __metaclass__ = ABCMeta
    
    @abstractmethod
    def __call__(self,x):
        raise NotImplementedError
       
    params = abstractproperty(doc='a sequence of the parameter names')     
    parvals = abstractproperty(doc='a sequence of the values in the parameters')       
    
    def _getPardict(self):
        """
        a dictionary of the parameter names and values
        """
        return dict([t for t in zip(self.params,self.parvals)]) 
    def _setPardict(self,val):
        self.parvals = [val[p] for p in self.params]
    pardict = property(_getPardict,_setPardict,doc="""
        a dictionary of the parameter names and values
        """)
    
    def inv(self,output,*args,**kwargs):
        """
        Compute the inverse of this model for the requested output
        
        It should raise a ModelTypeError if the model is not invertable for
        the provided data set
        """
        raise ModelTypeError('Model is not invertible')
    

class _AutoParameter(object):
    """
    Parameter representation used for objects instantiated with the
    AutoParamsMeta magic
    """
    def __init__(self,name,defaultvalue):
        self.name = name
        self.defaultvalue = defaultvalue
    
    def __get__(self,obj,owner):
        try:
            return getattr(obj,'_AutoParameter__'+self.name)
        except AttributeError: #if data doesn't exist, initialize to default and return it
             setattr(obj,'_AutoParameter__'+self.name,self.defaultvalue)
             return self.defaultvalue
    
    def __set__(self,obj,value):
        if not np.isscalar(value):
            raise ValueError('Parameters must be scalar values - type '+str(type(value))+' provided')
        setattr(obj,'_AutoParameter__'+self.name,value)
    
    def __delete__(self,obj):
        raise AttributeError("can't delete a parameter")

class AutoParamsMeta(ABCMeta):
    """
    Metaclass used to auto-generate parameters from 'f' function
    for FunctionModel classes
    
    This generates attributes for each of the 
    inputs of the function "f" (except self and x)
        
    When a model is instantiated, the arguments specify initial values for 
    the parameters, and any non-parameter kwargs will be passed into the 
    __init__ method of the model class
    
    if f is of the form f(self,x,*args), the first argument of the 
    constructor is taken to be the number of arguments that particular 
    instance should have, and the 'paramsname' class attribute can be used
    to specify the prefix for the name of the parameters (and can be 
    an iterator, in which case one of each name will be made for each var
    arg, in sequence order).  default values can be given by adding class 
    variables of the form "_param0_default"
    """
    def __init__(cls,name,bases,dct):
        #called on import of astro.models
        from inspect import getargspec
        
        super(AutoParamsMeta,cls).__init__(name,bases,dct)
        for c in cls.mro():
            if 'f' in c.__dict__:
                ffunc = c.__dict__['f']
                if callable(ffunc):
                    break
        else:
            raise KeyError('missing f function')
        args,varargs,varkw,defaults=getargspec(ffunc)
        if varkw is not None:
            raise SyntaxError("can't have kwargs in model function")
        
        #remove self if present, and the first argument, which is the data vector
        try:
            args.remove('self')
        except ValueError: # means the function is static or class method
            try:
                args.remove('cls')
            except ValueError: # means the function is static, which is still ok
                pass
        del args[0] #remove data vector
        
        if defaults is None:
            defaults=[]
        if len(args)!=len(defaults):
            defaults=list(defaults)
            for i in range(len(args)-len(defaults)): defaults.insert(0,1)
            
        for arg,d in zip(args,defaults):
            setattr(cls,arg,_AutoParameter(arg,d))
            
        if varargs is not None:
            cls._pars = None
            cls._statargs = list(args)
        else:
            cls._pars = tuple(args)
            
    def __call__(cls,*args,**kwargs):
        if cls._pars is None: #this is the case for *args in the function
            if len(args)>1:
                raise ValueError('must pass parameters with keywords at initializer if variable argument numbers are used')
            
            if hasattr(cls,'paramsname'):
                paramsnames = getattr(cls,'paramsname') 
            elif hasattr(cls,'paramsnames'):
                paramsnames = getattr(cls,'paramsnames')
            else:
                paramsnames =  ('p',)
            if isinstance(paramsnames,basestring):
                paramsnames = (paramsnames,)
            
            try:
                nparams=args[0] if 'nparams' not in kwargs else kwargs.pop('nparams')
            except IndexError:
                raise IndexError('No # of parameters found for variable-size function')
            objkwargs = dict([(k,kwargs.pop(k)) for k in kwargs.keys() if k not in cls._statargs if not any([k.startswith(paramsname) for paramsname in paramsnames])])
            cls._currnparams = nparams #this is set in case the constructor needs to know for some reason
            obj = super(AutoParamsMeta,AutoParamsMeta).__call__(cls,**objkwargs) #object __init__ is called here
            del cls._currnparams
            pars = list(cls._statargs)
            
            for i in range(nparams):
                for paramsname in paramsnames:
                    p = paramsname+str(i)
                    pars.append(p)
                    if hasattr(cls,'_'+p+'_default'): #let class variables of the form "_param_default" specify defaults for varargs
                        setattr(obj,p,getattr(cls,'_'+p+'_default'))
                    else:
                        setattr(obj,p,1) #default varargs to 1
            obj._pars = tuple(pars)
        else: #this is the case for fixed functions
            objkwargs=dict([(k,kwargs.pop(k)) for k in kwargs.keys() if k not in cls._pars])
            try:
                obj = super(AutoParamsMeta,AutoParamsMeta).__call__(cls,**objkwargs) #object __init__ is called here
            except TypeError,e:
                if len(e.args)>0 and 'object.__new__() takes no parameters' == e.args[0]:
                    raise TypeError('invalid parameter in model constructor:'+str(objkwargs.keys()))
                else:
                    raise
            
        #set initial values
        if len(args)+len(kwargs) > len(obj.params):
            raise TypeError('Too many args and kwargs for the parameters')
        
        pars=list(obj.params)
        for k,v in kwargs.iteritems():
            del pars[pars.index(k)]
            setattr(obj,k,v)
        for p,v in zip(pars,args):
            setattr(obj,p,v)
            
        return obj
    
    
class FunctionModel(ParametricModel):
    """
    A base class for models that use a single function to map a
    numpy array input to an output (the function must be specified as the 
    "f" method)
    
    The following attributes *must* be defined:
    
    * 'f': a method that takes an array as the first argument and 
         returns another array
    * '_pars': a sequence of strings that define the names of attributes 
      that are to be treated as the parameters for the model. If these are
      not defined, they will be initialized to the "defaultparval" value
    
    * '_filterfunc': a function that performs any processing of inputs and 
      outputs.  Should call f and return f's return value.
      
    If type-checking is to be performed on the input, it should be performed
    in __call__ (see docstring for __call__), but any mandatory input 
    conversion should be done in _filterfunc, instead
    """
    
    defaultparval = 1
    fitteddata = None
    
    @abstractmethod
    def f(self,x,*params):
        """
        This function MUST be overriden in subclasses.  It is
        interpreted as the function that takes an array (or array-castable)
        as the first argument and returns an array of output values 
        appropriate for the model.
        
        model parameters are passed in as the rest of the arguments, in the 
        order they are given in the _pars sequence.
        """
        raise NotImplementedError
    
    
    
    def _filterfunc(self,*args,**kwargs):
        """
        this single-use function is in place to not need an __init__ method 
        to initially set the calling function
        """
        self._filterfunc = self.f
        return self.f(*args,**kwargs)
    
    def __call__(self,x):
        """
        call the function on the input x with the current parameters and return
        the result.
        
        if subclassing to do type-checking, the function should return the
        result of self._filterfunc(input,*self.parvals) or raise a 
        ModelTypeError
        """
        arr = np.array(x,copy=False,dtype=float)
        return self._filterfunc(arr,*self.parvals)
    
    _pars=tuple() #default empty parameter sequence
        
    @property
    def params(self):
        """
        a tuple of the parameter names
        """
        return self._pars
    
    def _getParvals(self):
        try:
            return tuple([getattr(self,a) for a in self._pars])
        except AttributeError:
            self._autoInitPars()
            return self._getParvals()
    def _setParvals(self,newpars):
        if len(newpars)>len(self._pars):
            raise ValueError('too many new parameters')
        for a,v in zip(self._pars,newpars):
            setattr(self,a,v)        
    parvals = property(_getParvals,_setParvals,doc='a list of the values in the parameters') 
    
    def _getPardict(self):
        try:
            return dict([(a,getattr(self,a)) for a in self._pars])
        except AttributeError:
            self._autoInitPars()
            return self._getPardict()
    def _setPardict(self,newpardict):
        for k in newpardict.keys():
            if k not in self._pars:
                raise KeyError('No parameter %s found'%k)
        for k,v in newpardict.iteritems():
            setattr(self,k,v)
    pardict = property(_getPardict,_setPardict,doc='a dictionary of the parameter names and values')
    
    def _autoInitPars(self):
        """
        called to generate parameters if they are missing
        """
        for p in self._pars:
            setattr(self,p,self.defaultparval)
            
    def fitData(self,x,y,method=None,fixedpars=None,weights=None,contraction='sumsq',
                 updatepars=True,fitf=False,savedata=True,**kwargs):
        """
        Adjust the parameters of the FunctionModel to fit the provided data 
        using algorithms from scipy.optimize
        
        The data to fit is provided by the first to arguments -  'x' is
        the input array at which to evaluate the model, and 'y' gives 
        the value the model should have at that point.  If the output of the
        model does not match the shape of y, a ModelTypeError will be raised. 
        
        method can be any of the optimize functions (except constrained or
        scalar optimizers) or 'custom'.  If 'custom', the _custumFit method
        of the model will be called as 
        self._customFit(x,y,fixedpars=fixedpars,weights=weights,**kwargs) 
        default is 'custom', or if not present, 'leastsq'
        
        fixedpars is a sequence of parameter names to leave fixed.  If it is
        None, the fixed parameters are inferred from self.fixedpars (or 
        all will be free parameters if self.fixedpars is absent)
        
        weights is an array of points that must match the output (or None for
        equal weights)
        
        contraction applies for all except the 'leastsq' method  (for which only
        'frac' is meaningful) and is the technique used to convert vectors to
        figures of merit.  this is composed of multiple string segments:
        
        #. these will be applied to each element of the vector first:
        
           - 'sq': square
           - 'abs':absolute value
           - '':raw value
          
        #. the contraction is performed after:
        
           - 'sum': sum of all the elements
           - 'median': median of all the elements
           - 'mean': mean of all the elements
           - 'prod': product of all the elements 
           
        * optionally,the string can include 'frac' to use the fractional 
          version of the differnce vector instead of raw values
        
        kwargs go into the fitting function
        
        returns the vector of the best fit parameters, and sets the parameters 
        if updatepars is True
        
        the full output is available is self.lastfit
        
        if savedata is true, the input fit data will be available in 
        self.fitteddata as an (x,y) tuple
        
        see also:getMCMC
        """
        from scipy import optimize as opt
        
        if fitf:
            fitfunc = self.f
        else:
            fitfunc = self._filterfunc
        
        if fitfunc(x,*self.parvals).shape != y.shape:
            raise ModelTypeError('y array does not match output of model for input x')
        if weights is None:
            w = 1
        else:
            w = np.array(weights,copy=False)
            if w.shape != y.shape:
                raise ModelTypeError('weights shape does not match y')
            w = w.ravel()
        y = y.ravel()
        
        if method is None:
            if '_customFit' in self.__class__.__dict__:
                method = 'custom'
            else:
                method = 'leastsq'
            
            
        if fixedpars is None:
            fixedpars = self.fixedpars if hasattr(self,'fixedpars') else ()
            
        ps=list(self.params)
        v=list(self.parvals) #initial guess
        
        
        
        if method == 'custom':
            res = self._customFit(x,y,fixedpars=fixedpars,weights=weights,**kwargs) 
            #ensure that res is at least a tuple with parameters in elem 0
            from operator import isSequenceType
            if not isSequenceType(res[0]):
                res = (res,)
                
            if fixedpars:
                for p in fixedpars:
                    i=ps.index(p)
                    del ps[i]
                    del v[i]
        else:
            kwargs['full_output'] = 1
            
            if fixedpars:
                for p in fixedpars:
                    i=ps.index(p)
                    del ps[i]
                    del v[i]
                
                #make a function of signature f(x,v) where v are the parameters to be fit
                pdict=dict([(p,getattr(self,p)) for p in fixedpars])
                def f(x,v):
                    pdict.update(dict(zip(ps,v)))
                    #return fitfunc(x,**pdict)
                    params = [pdict[a] for a in self._pars]
                    return fitfunc(x,*params).ravel()
            else:
                f=lambda x,v:fitfunc(x,*v).ravel()
                
            if method == 'leastsq':
                if 'frac' in contraction:
                    g=lambda v,x,y:w*(1-f(x,v)/y)
                else:
                    g=lambda v,x,y:w*(y-f(x,v))
                res=opt.leastsq(g,v,(x,y),**kwargs)
            else:
                if 'frac' in contraction:
                    if 'sq' in contraction:
                        def g1(v,x,y):
                            diff=1-f(x,v)/y
                            return diff*diff
                    elif 'abs' in contraction:
                        def g1(v,x,y):
                            diff=1-f(x,v)/y
                            return np.abs(diff)
                    else:
                        def g1(v,x,y):
                            diff=1-f(x,v)/y
                            return diff
                else:
                    if 'sq' in contraction:
                        def g1(v,x,y):
                            diff=y-f(x,v)
                            return diff*diff
                    elif 'abs' in contraction:
                        def g1(v,x,y):
                            diff=y-f(x,v)
                            return np.abs(diff)
                    else:
                        def g1(v,x,y):
                            diff=y-f(x,v)
                            return np.diff
                if 'sum' in contraction:
                    g=lambda v,x,y:np.sum(w*g1(v,x,y),axis=None)
                elif 'mean' in contraction:
                    g=lambda v,x,y:np.mean(w*g1(v,x,y),axis=None)
                elif 'median' in contraction:
                    g=lambda v,x,y:np.median(w*g1(v,x,y),axis=None)
                elif 'prod' in contraction:
                    g=lambda v,x,y:np.prod(w*g1(v,x,y),axis=None)
                else:
                    raise ValueError('no valid contraction method provided')
                    
                if method == 'fmin':
                    res=opt.fmin(g,v,(x,y),**kwargs)
                elif method == 'fmin_powell':
                    res=opt.fmin_powell(g,v,(x,y),**kwargs)
                elif method == 'fmin_cg':
                    #TODO:smartly include derivative
                    res=opt.fmin_cg(g,v,args=(x,y),**kwargs)
                elif method == 'fmin_bfgs':
                    #TODO:smartly include derivative
                    res=opt.fmin_bfgs(g,v,args=(x,y),**kwargs)
                elif method == 'fmin_ncg':
                    raise NotImplementedError
                    #TODO:needs gradient and hessian
                    opt.fmin_ncg
                elif method == 'anneal' or method == 'global':
                    res=opt.anneal(g,v,args=(x,y),**kwargs)
                elif method == 'brute':
                    raise NotImplementedError
                    #TODO: set parrange smartly
                    res=opt.brute(g,parrange,(x,y),**kwargs)
                else:
                    raise ValueError('Unrecognzied method %s'%method)
            
        self.lastfit = res
        v=res[0] #assumes output is at least a tuple - needs "full_output=1 !"
        
        try:
            v[0]
        except IndexError: #only one parameter
            v=np.array([v])
            
        if updatepars:
            for par,newv in zip(ps,v):
                setattr(self,par,newv)
                
        if savedata: 
            self.fitteddata = (x,y)
        
        return v
    
    def _customFit(self,x,y,fixedpars=(),weights=None,**kwargs):
        """
        Must be overridden to use 'custom' fit technique
        
        fixedpars will be a sequence of parameters that should be kept fixed
        for the fitting (possibly/typically empty)
        
        should return a tuple where the first element gives the best fit
        parameter vector 
        """
        raise NotImplementedError('No custom fit function provided for this model')
    
    def stdData(self,x=None,y=None):
        """
        determines the standard deviation of the model from the supplied data
        
        if x or y are None, they are determined from the pre-fitted data
        """
        if x is None or y is None:
            if self.fitteddata is None:
                raise ValueError('must either specify data or save fitted data')
            x,y = self.fitteddata
        
        if self(x).shape != y.shape:
            raise ModelTypeError('y array does not match output of model for input x')
        
        return np.std(y-self(x),ddof=len(self.params))
    
    def residuals(self,x=None,y=None,retdata=False):
        """
        returns residuals of the provided data against the model (e.g.
        y-model(x) ).  
        
        If x or y are None, data are determined from the already-fit data
        
        returns x,y,residuals if retdata is True, otherwise just residuals
        """
        if x is None or y is None:
            if self.fitteddata is None:
                raise ValueError('must either specify data or save fitted data')
            x,y = self.fitteddata
        
        if self(x).shape != y.shape:
            raise ModelTypeError('y array does not match output of model for input x')
        if retdata:
            return x,y,y-self(x)
        else:
            return y-self(x)
    
    def chi2Data(self,x=None,y=None):
        """
        Determines the chi-squared statistic for the data assuming this 
        model.
        
        
        returns chi2,reducedchi2,p-value
        """
        from scipy.stats import chisqprob
        
        if x is None or y is None:
            if self.fitteddata is None:
                raise ValueError('must either specify data or save fitted data')
            x,y = self.fitteddata
        
        if self(x,*self.parvals).shape != y.shape:
            raise ModelTypeError('y array does not match output of model for input x')
        
        n=len(y)
        m=len(self.params)
        dof=n-m-1 #extra 1 because the distribution must sum to n
        
        chi2=(y-self(x))**2/self(x)
        chi2=np.sum(chi2*chi2)
        
        return chi2,chi2/dof,chisqprob(chi2,dof)
    
    def bootstrapFits(self,x=None,y=None,n=250,plothist=False):
        """
        uses the fitData function to fit the function and then uses the
        "bootstrap" technique to estimate errors - that is, use sampling
        w/replacement
        
        x and y are the data to fit, n is the number of iterations to perform,
        and plothist can be used to 
        
        Note that sampling is only perfermed on the last index of the input
        and output arrays.
        """
        
        if x is None or y is None:
            if self.fitteddata is None:
                raise ValueError('must either specify data or save fitted data')
            x,y = self.fitteddata
        
        if self(x).shape != y.shape:
            raise ModelTypeError('y array does not match output of model for input x')
        
        if y.shape[-1] != x.shape[-1]:
            raise ModelTypeError('last index does not match for input and output')
        
        if prefit:
            self.fitData(x,y,**kwargs)
            
        for xd,yd in zip(xi,yi):
            vs.append(self.fitData(xd,yd,updatepars=False,**kwargs))
            
        d=dict([(p,v) for p,v in zip(self.params,np.array(vs).T)])
        
        if plothist:
            import matplotlib.pyplot as plt
            #want to generate as square as possible
            nr=nc=int(len(self.params)**0.5)
            if nr*nc < len(self.params):
                nr+=1
            if nr*nc < len(self.params):
                nc+=1
                
            for i,p in enumerate(self.params):
                plt.subplot(nr,nc,i+1)
                plt.hist(d[p],bins=n//20)
                plt.xlabel(p)
                plt.ylabel('N')
                plt.title('Median$=%3.3f$ $\\sigma=%3.3f$ Fit$=%3.3f$'%(np.median(d[p]),np.std(d[p]),self.pardict[p]))
        
        return d
    
    def getMCMC(self,x,y,priors={},datamodel=None):
        """
        Generate an object to fit the data using Markov Chain Monte 
        Carlo sampling.  
        
        The data to be fit is provided in the x and y arguments.
        
        To specify the priors, either supply pymc.Stochastric objects, a 2-tuple 
        (uniform lower and upper), a scalar > 0 (gaussian w/ the center given by 
        the current value and sigma provided by the scalar), or 0 (poisson with 
        k set by the current value)
        
        Any missing priors will raise a ValueError
        
        datamodel can be:
        
        * None: a normal distribution with sigma given by the data's standard 
          deviation is used as the data model
        * a tuple: (dist,dataname,kwargs)the first element is the 
          pymc.distribution to be used as the distribution representing the data
          and the second is the name of the argument to be associated with the 
          FunctionModel1D's output, and the third is kwargs for the distribution 
          ("observed" and "data" will be ignored, as will the data argument)
        * a scalar or sequence of length == data: a normal distribution is used 
          with sigma specified by the scalar/sequence
        
        returns a pymc.MCMC object
        
        *Note that this function requires PyMC (http://code.google.com/p/pymc/)*
        """
        import pymc
        from operator import isSequenceType
        from inspect import getargspec
        from types import MethodType
        
        if set(priors.keys()) != set(self.params):
            raise ValueError("input priors don't match function params")
        
        d={}
        for k,v in priors.iteritems():
            if isinstance(v,pymc.StochasticBase):
                d[k]=v
            elif isSequenceType(v):
                if len(v) == 2:
                    d[k]=pymc.distributions.Uniform(k,v[0],v[1])
                else:
                    raise ValueError("couldn't understand sequence "+str(v) )
            elif v > 0:
                d[k] = pymc.distributions.Normal(k,self.pardict[k],1.0/v/v)
            elif v == 0:
                d[k] = pymc.distributions.Poisson(k,self.pardict[k])
            else:
                raise ValueError("couldn't interpret prior "+str(v))
        
        funcdict=dict(d)
        if type(self.f) is MethodType:
            xstr = getargspec(self.f)[0][1]
        else:
            assert callable(self.f),'object function is not a callable'
            xstr = getargspec(self.f)[0][0] 
        funcdict[xstr]=x
        funcdet=pymc.Deterministic(name='f',eval=self.f,parents=funcdict,doc="FunctionModel1D function")
        d['f'] = funcdet
        
        if type(datamodel) is tuple:
            distobj,dataarg,kwargs=datamodel
            if 'name' not in kwargs:
                kwargs['name'] = 'data'
                
            kwargs[dataarg] = funcdet
            kwargs['observed'] = True
            kwargs['value'] = y
            
            datamodel = distobj(**kwargs)
        else:
            if datamodel is None:
                sig = np.std(y)
            else:
                sig = datamodel
            datamodel = pymc.distributions.Normal('data',mu=funcdet,tau=1/sig/sig,observed=True,value=y)
        d[datamodel.__name__ ]=datamodel
        
        return pymc.MCMC(d)

class FunctionModel1D(FunctionModel):
    
    """
    This class is the base for 1-dimensional models with parameters that are 
    implemented as python functions.
    
    Subclassing:
    The following method MUST be overridden in a subclass:
    
    * f(self,x,...)
    
    The following methods may be overridden for speed of some operations - pars
    should be accessed with self.pardict, self.parvals, or by properties/name :
    
    * integrate(self,lower,upper): integrate the model from lower to upper
    * derivative(self,x,dx): derivative of the model at x, optinally using 
      spacing dx
    * inv(yval,*args,**kwargs): inverse of the model at the requested yvalue
    * _customFit(x,y,fixedpars=(),weights=None,**kwargs): implement a
      specialized fitting algorithm for this model that will be called
      if fitData is called with method='custom'
    
    The following attributes may be set for additional information:
    * xaxisname: name of the input axis for this model
    * yaxisname: name of the output axis for this model
    * rangehint: a hint for the relevant range for this model as 
    a (lower,upper) tuple (or None if no particular range is relevant)
    """    
    defaultIntMethod = 'quad'
    defaultInvMethod = 'brentq'
    xaxisname = None
    yaxisname = None
    rangehint = None
    
    def __call__(self,x):
        """
        call the function on the input x,which will be flattened.  If not 1D,
        the output will be reshaped to the input
        """
        arr = np.array(x,copy=False,dtype=float)
        res = self._filterfunc(arr.ravel(),*self.parvals)
        return res.reshape(arr.shape)
    
    def inv(self,yval,*args,**kwargs):
        """
        Find the x value matching the requested y-value.  
        (note that yval must be a scalar)
        
        typical usage is inv(yval,a,b,method='brentq')
        
        the kwarg 'method' can be any of the root finders from scipy.optimize 
        scalar solvers are recommended (default is brentq or newton).  'method' 
        can also be a function that should take f(g(x),*args,**kwargs) and 
        return where g(x) is 0
        
        *args and **kwargs are passed into the minimizer
        """    
        import scipy.optimize
        
        if not np.isscalar(yval):
            raise ModelTypeError('generic 1D inverter can only accept scalar inputs')
        
        if len(args) == 0:
            args=[0]
            method = kwargs.pop('method','newton')
        elif len(args) == 1:
            method = kwargs.pop('method','newton')
        else:
            method = kwargs.pop('method','brentq')
            
        if isinstance(method,basestring):
            f = getattr(scipy.optimize,method)
        else:
            f = method
        
        if kwargs.pop('abs',False):
            g = lambda(x):np.abs(self(x)-yval)
        else:
            g = lambda(x):self(x)-yval
        
        return f(g,*args,**kwargs)
    
    def minimize(self,x0,method='fmin',**kwargs):
        """
        Finds a local minimum for the model
        
        x0 is the location to start the search
        method can be 'fmin' or 'fmin_powell' (from scipy.optimize)
        kwargs are passed into the scipy.optimize function
        """
        return self._optimize(x0,'min',method,**kwargs)
    
    def maximize(self,x0,method='fmin',**kwargs):
        """
        Finds a local maximum for the model
        
        x0 is the location to start the search
        method can be 'fmin' or 'fmin_powell' (from scipy.optimize)
        kwargs are passed into the scipy.optimize function
        """
        return self._optimize(x0,'max',method,**kwargs)
    
    def findroot(self,x0,method='fmin',**kwargs):
        """
        Finds a root for the model (i.e. location where the model is 0)
        
        x0 is the location to start the search
        method can be 'fmin' or 'fmin_powell' (from scipy.optimize)
        kwargs are passed into the scipy.optimize function
        """
        return self._optimize(x0,'root',method,**kwargs)
    
    def findval(self,val,x0,method='fmin',**kwargs):
        """
        Finds where the model is equal to the value given by the val argument
        
        x0 is the location to start the search
        method can be 'fmin' or 'fmin_powell' (from scipy.optimize)
        kwargs are passed into the scipy.optimize function
        """
        kwargs['valtofind'] = val
        return self._optimize(x0,'val',method,**kwargs)
        
    def _optimize(self,x0,type,method,**kwargs):
        """
        find an optimal value for the model - x0 is where to start the search
        type can be 'min','max','root',or 'saddle'
        method can be 'fmin' or 'fmin_powell'
        """
        from scipy.optimize import fmin,fmin_powell
        
        if type == 'min':
            g=lambda *args,**kwargs:self.f(*args,**kwargs)
        elif type == 'max':
            g=lambda *args,**kwargs:-1*self.f(*args,**kwargs)
        elif type == 'root':
            g=lambda *args,**kwargs:np.abs(self.f(*args,**kwargs))
        elif type == 'val':
            val = kwargs.pop('valtofind')
            g=lambda *args,**kwargs:np.abs(self.f(*args,**kwargs)-val)
        elif type == 'saddle':
            raise NotImplementedError
        else:
            raise ValueError('Unrecognized optimization type')
        
        if method == 'fmin':
            res = fmin(g,x0,tuple(self.parvals),**kwargs)
        elif method == 'fmin_powell':
            res = fmin_powell(g,x0,tuple(self.parvals),**kwargs)
        else:
            raise ValueError('Unrecognized method')
        
        self.lastOpt = res
        return res[0]
    
    
        
    def plot(self,lower=None,upper=None,n=100,integrate=None,clf=True,logplot='',
              powerx=False,powery=False,deriv=None,data='auto',*args,**kwargs):
        """
        plot the model function from lower to upper with n samples
        
        integrate controls whether or not to plot the integral of the function -
        if True, the base of the integral is taken to be lower, if False, upper,
        no integration if None, and otherwise, the base is the argument value.
        It can also be 's', 'spherical','c',or 'circular' for the 
        appropriate types of integration
        
        extra args and kwargs go into the matplotlib plot function
        
        data is either an x,y pair of data points or a dictionary of kwargs into 
        scatter. If it is 'auto', the last data input to fitData will be used
        (if savedata was true).  If it evaluates to False, no data will be 
        plotted and lower and upper must be set
        
        logplot determines whether or not to plot on a log scale, and powerx and
        poweru determine if the model points should be used as powers (base 10)
        before plotting
        """
        from matplotlib import pyplot as plt
        from operator import isMappingType
        
        isinter = plt.isinteractive()
        try:
            plt.ioff()
            if data is 'auto':
                if self.fitteddata:
                    data = self.fitteddata
                else:
                    data = None
                    
            if data is not None:
                if lower is None:
                    lower=np.min(data[0])
                if upper is None:
                    upper=np.max(data[0])
            
            if lower is None or upper is None:
                rh = self.rangehint
                if rh is None:
                    raise ValueError("Can't choose limits for plotting without data or a range hint")
                else:
                    if lower is None:
                        lower = rh[0]
                    if upper is None:
                        upper = rh[1]
            
            if 'x' in logplot:
                x = np.logspace(np.log10(lower),np.log10(upper),n)
            else:
                x = np.linspace(lower,upper,n)
            
            if powerx:
                x=10**x
                
            if integrate is None and not deriv:
                y = self(x)
            elif deriv:
                if integrate is not None:
                    raise ValueError("can't do derivative and integral simultaneously")
                y=np.array([self.derivative(v,np.abs(upper-lower)/(10*n)) for v in x])
            else: #integrate is not None
                intfunc = self.integrate
                if integrate is True:
                    base = lower
                elif integrate is False:
                    base = upper
                elif isinstance(integrate,basestring):
                    if integrate.startswith('s'): #spherical
                        intfunc = self.integrateSpherical
                        base = 0
                    elif integrate.startswith('c'): #circular
                        intfunc = self.integrateCircular
                        base = 0
                    else:
                        raise ValueError('unrecognized integrate string')
                else:
                    base = float(integrate)
                y=np.array([intfunc(base,v) for v in x])
                                
            if powery:
                y= 10**y
            
            if clf:
                plt.clf()
            if 'x' in logplot and 'y' in logplot:
                plt.loglog(x,y,*args,**kwargs)
            elif 'x' in logplot:
                plt.semilogx(x,y,*args,**kwargs)
            elif 'y' in logplot:
                plt.semilogy(x,y,*args,**kwargs)
            else:
                plt.plot(x,y,*args,**kwargs)
            
            if np.any(data):
                if isMappingType(data):
                    if clf and 'c' not in data:
                        data['c']='g'
                    plt.scatter(**data)
                else:
                    if clf and len(data)<4:
                        data=list(data)
                        if len(data) < 3:
                            data.append(20)
                        data.append('r')
                    plt.scatter(*data)
            plt.xlim(lower,upper)
            
            if self.xaxisname:
                plt.xlabel(self.xaxisname)
            if self.yaxisname:
                plt.ylabel(self.yaxisname)
                
            if isinter:
                    plt.draw()
                    plt.show()
        finally:
            plt.interactive(isinter)
    
    #Can Override:
    def integrate(self,lower,upper,method=None,n=None,jac=None,**kwargs):
        """
        This will numerically integrate the model function from lower to upper
        using scipy.integrate techniques
        
        method can be specified (a function from scipy.integrate) or if None,
        self.defaultIntMethod will be used
        
        n is either the number of data values or the order for ordered methods,
        or if sequence,will be used as the integration x-values (and lower/upper
        are ignored)
        
        jac is the jacobian factor as a function f(x,*params)
        
        returns value
        most methods will also store their result to "lastintegrate"
        
        if subclassing, this should be overwritten with a function of the form
        integrate(lower,upper,[args])
        """
        
        #TODO:vectorize when needed
        
        import scipy.integrate as itg
        if method is None:
            method=self.defaultIntMethod
        
        e,d=None,None
        
        ps=tuple(self.parvals)
        if jac:
            def f(x,*pars):
                return jac(x,*pars)*self.f(x,*pars)
        else:
            f=self.f
        
        if method=='quad':
            res=itg.quad(f,lower,upper,args=ps,full_output=1,**kwargs)
            if len(res) == 4:
                v,e,d,m = res
                from warnings import warn
                warn('Integration message: %s'%m)
                print 'Integration message:',m
        #use these for 2d and 3d
        #elif method=='dblquad':
        #    raise NotImplementedError
        #elif method=='tplquad':
        #    raise NotImplementedError
        elif method=='fixed_quad':
            res=itg.fixed_quad(f,lower,upper,ps,5 if n is None else n,**kwargs)
        elif method=='quadrature':
            res=itg.quadrature(f,lower,upper,ps,**kwargs)
        elif method=='romberg':
            res=itg.romberg(f,lower,upper,ps,**kwargs)
        else: #sampled techniques
            if n is None:
                n=100
            if np.isscalar(n):
                x=np.linspace(lower,upper,n)
            else:
                x=np.array(n)
            y=f(x,*ps)
            if method=='trapz':
                res=itg.trapz(y,x,**kwargs)
            elif method=='cumtrapz':
                res=itg.cumtrapz(y,x,**kwargs)
            elif method=='simps':
                res=itg.simps(y,x,**kwargs)
            elif method=='romb':
                res=itg.simps(y,np.convolve(x,[1,-1],mode='same').mean(),**kwargs)
            else:
                raise ValueError('unrecognized integration method')
        
        
        self.lastintegrate = res
        return res if np.isscalar(res) else res[0]
    
    def integrateCircular(self,lower,upper,*args,**kwargs):
        """
        This is an alias for self.integrate with jacobian set for a azimuthally
        symmetric 2D radial profile
        """
        if 'jac' in kwargs:
            kwargs['jac'] = lambda x,*params:kwargs['jac'](x,*params)*x*2.0*pi
        else:
            kwargs['jac'] = lambda x,*params:x*2.0*pi
        return self.integrate(lower,upper,*args,**kwargs)
    
    def integrateSpherical(self,lower,upper,*args,**kwargs):
        """
        This is an alias for self.integrate with jacobian set for a spherically
        symmetric 3D radial profile
        """
        if 'jac' in kwargs:
            kwargs['jac'] = lambda x,*params:kwargs['jac'](x,*params)*x*x*4.0*pi
        else:
            kwargs['jac'] = lambda x,*params:x*x*4.0*pi
        return self.integrate(lower,upper,*args,**kwargs)
        
    def derivative(self,x,dx=1):
        """
        the derivative at x
        
        if overridden in a subclass, the signature should be
        derivative(self,x,dx=1) , but dx may be ignored
        """
        return (self(x+dx)-self(x))/dx
    
    
    #TODO:move this up into FunctionModel
    def setCall(self,type=None,xtrans=None,ytrans=None,**kwargs):
        """
        sets the type of function evaluation to occur when the model is called
        
        type can be:
        *None: basic function evaluation
        *derivative: derivative at the location
        *integrate: integral - specify 'upper' or 'lower' kwarg and
                    the evaluation location will be treated as the
                    other bound.  If neither is given, lower=0 is assumed
        *integrateCircular: same as integrate, but using polar jacobian
        *integrateSpherical: same as integrate, but using spherical jacobian
        
        xtrans and ytrans are functions applied to either the input call (for x)
        or the output (for y) - they can also be strings:
        *'log':base-10 logarithm
        *'ln':base-e logarithm
        *'pow':10**
        *'exp':e**
        
        kwargs are passed into the type requested, and the call will occur on 
        
        note that if the model object is called directly in an overridden 
        method that is used in the new call, it probably won't work
        """
        from types import MethodType
        import inspect
        from functools import partial
        
        transmap={'log':np.log10,'ln':np.log,'pow':partial(np.power,10),'exp':np.exp}
        xts,yts = xtrans,ytrans
        if isinstance(xtrans,basestring):
            xtrans = transmap[xtrans]
        if isinstance(ytrans,basestring):
            ytrans = transmap[ytrans]
            
        if type is None:
            if xtrans and ytrans: 
                self._filterfunc = MethodType(lambda self,x,*pars:ytrans(self.f(xtrans(x),*pars)),self,self.__class__)
            elif xtrans:
                self._filterfunc = MethodType(lambda self,x,*pars:self.f(xtrans(x),*pars),self,self.__class__)
            elif ytrans:
                self._filterfunc = MethodType(lambda self,x,*pars:ytrans(self.f(x,*pars)),self,self.__class__)
            else:
                self._filterfunc = self.f
        else:
            try:
                newf = getattr(self,type)
                
                if not callable(newf):
                    raise AttributeError
            except AttributeError:
                raise AttributeError('function %s not found in %s'%(type,self))
                
            if 'integrate' in type:
                if 'upper' in kwargs and 'lower' in kwargs:
                    raise ValueError("can't do integral with lower and upper both specified")
                elif 'upper' in kwargs:
                    xkw = 'lower'
                elif  'lower' in kwargs:
                    xkw = 'upper'
                else: 
                    kwargs['lower']=0
                    xkw = 'upper'
                    #raise ValueError("can't do integral without lower or upper specified")
                
                #TODO:undo this once integrateSpherical is vectorized
                def vecf(x):
                    kwargs[xkw] = x
                    return newf(**kwargs)
                vecf = np.vectorize(vecf)
                
                
                if xtrans and ytrans: 
                    def callfunc(self,x,*pars):
                        self.parvals = pars
                        return ytrans(vecf(xtrans(x)))
                elif xtrans:
                    def callfunc(self,x,*pars):
                        self.parvals = pars
                        return vecf(xtrans(x))
                elif ytrans:
                    def callfunc(self,x,*pars):
                        self.parvals = pars
                        return ytrans(vecf(x))
                else:
                    def callfunc(self,x,*pars):
                        #TODO:test cost of par-setting
                        self.parvals = pars
                        return vecf(x)
                
            else:    
                
                fargs, fvarargs, fvarkws, fdefaults = inspect.getargspec(newf)
                    
                for arg in fargs:
                    if arg not in kwargs and arg !='self':
                        xkw = arg
                        break
                else:
                    raise ValueError('function with no arguments attempted in setCall')
                if xtrans and ytrans: 
                    def callfunc(self,x,*pars):
                        #TODO:test cost of par-setting
                        self.parvals = pars
                        kwargs[xkw] = xtrans(x)
                        return ytrans(newf(**kwargs))
                elif xtrans:
                    def callfunc(self,x,*pars):
                        #TODO:test cost of par-setting
                        self.parvals = pars
                        kwargs[xkw] = xtrans(x)
                        return newf(**kwargs)
                elif ytrans:
                    def callfunc(self,x,*pars):
                        #TODO:test cost of par-setting
                        self.parvals = pars
                        kwargs[xkw] = x
                        return ytrans(newf(**kwargs))
                else:
                    def callfunc(self,x,*pars):
                        #TODO:test cost of par-setting
                        self.parvals = pars
                        kwargs[xkw] = x
                        return newf(**kwargs)
                
            self._filterfunc = MethodType(callfunc,self,self.__class__)
            
        self._filterfunctype = (type,xts,yts)
        
    def getCall(self):
        """
        returns the type of evaluation to perform when this model is called - 
        a string like that of the type passed into `setCall`, or None if
        the model function itself is to be called.
        """
        if hasattr(self,'_filterfunctype'):
            return self._filterfunctype
        else:
            return None
        

class FunctionModel1DAuto(FunctionModel1D):
    """
    A FunctionModel1D that infers the parameters from the f-function
    
    equivalent to simply setting the metaclass to AutoParamsMeta
    """
    __metaclass__ = AutoParamsMeta

class CompositeModel1D(FunctionModel1D):
    """
    This model contains a group of FunctionModel1D objects and evaluates them
    as a single model.
    
    The models can either be FunctionModel1D objects, FunctionModel1D classes,
    or a string (in the later two cases, new instances will be generated)
    
    parameter names are of the form 'A0' and 'A1' where A is the parameter
    name and the number is the sequential number of the model with that
    parameter.  If autoshorten is True, the suffix will be removed if there
    is only one of that parameter
    
    parnames is a dictionary that maps from names of the form 'A0' to a 
    different name for the parameter.  If a parameter with the name already
    exists, a ValueError will be raised.
    
    the operations can be any valid python operator, or a sequence of operators
    to apply (e.g. ['+','*','+'] will do mod1+mod2*mod3+mod4), or a string
    giving the expression to be evaluated, with  'm' in places where
    the evaluated models (in order) should go (e.g. 'm + m * m + m' will do
    mod1+mod2*mod3+mod4)    
    
    any extra kwargs will be used to specify default values of the parameters
    """
    
    #TODO:initial vals
    def __init__(self,models=[],operation='+',parnames={},autoshorten=True,
                  **parvals):
        from inspect import isclass
        
        self.__dict__['_pars'] = tuple() #necessary for later when getattr is invoked
        
        mods = []

        for m in models:
            if isinstance(m,FunctionModel1D):
                pass
            elif isinstance(m,basestring):
                m = get_model(m)()
            elif isclass(m) and issubclass(m,FunctionModel1D):
                m = m()
            else:
                raise ValueError('Supplied object is not a function model')
            mods.append(m)
            
        self._models = tuple(mods)
        
        if isinstance(operation,basestring):
            if len(operation.strip()) == 1:
                operation = [operation for i in range(len(mods)-1)]
            else:
                operation = operation.split('m')[1:-1]
        elif len(operation) != len(mods)-1:
            raise ValueError('impossible number of operations')
        
        
        self._ops = tuple(operation)
            
        oplst = ['mval[%i]%s'%t for t in enumerate(self._ops)]
        oplst += 'mval[%i]'%len(oplst)
        self._opstr = ''.join(oplst)
        
        args = []
        argmap = {}
        #add all parameters with suffixes for their model number
        for i,m in enumerate(self._models):
            for p in m.params:
                argn = p+str(i)
                args.append(argn)
                argmap[argn] = (i,p) 
                
        if parnames:
            for k,v in parnames.iteritems():
                try:
                    i = args.index(k)
                except ValueError:
                    raise KeyError('parameter %s not present'%k)
                if v in args:
                    raise ValueError('attempted to specify a replacement parameter name that already exists')
                args[i] = v
                argmap[v] = argmap[k]
                del argmap[k]
        else:
            parnames = {}
                        
        #remove suffixes if they are unique
        if autoshorten:
            cargs = list(args)
            for i,a in enumerate(cargs):
                if a not in parnames.values():
                    argname = argmap[a][1]
                    for j,a2 in enumerate(cargs):
                        if a2.startswith(argname) and i != j:
                            break
                    else:
                        argmap[argname] = argmap[a]
                        del argmap[a]
                        args[i] = argname
            
        self._pars = tuple(args)
        self._argmap = argmap
        
        self._filters = None
        
        for k,v in parvals.iteritems():
            setattr(self,k,v)
    
    def __getattr__(self,name):
        if name in self._pars:
            i,n = self._argmap[name]
            return getattr(self._models[i],n)
        raise AttributeError("'%s' has no attribute '%s'"%(self,name))
    
    def __setattr__(self,name,val):
        if name in self._pars:
            i,n = self._argmap[name]
            setattr(self._models[i],n,val)
        else:
            self.__dict__[name] = val
    
    def f(self,x,*args):
        #TODO: find out if the commented part can be sometimes skipped somehow
        for p,a in zip(self.params,args):
            setattr(self,p,a)
        mval = [m.f(x,*m.parvals) for m in self._models]
        res = eval(self._opstr)
        if self._filters is None:
            return res
        else:
            for filter in self._filters:
                res = filter(res)
            return res
        
    def addFilter(self,filter):
        """
        This adds a function to be applied after the model is evaluated
        """
        if self._filters is None:
            self._filters = []
        
        if not callable(filter):
            raise ValueError('input filter is not a function')
        
        self._filters.append(filter)
        
    def clearFilters(self):
        """
        this clears all previously added filters
        """
        self._filters = None
        
    def addLowerBoundFilter(self,bound):
        def bndfunc(x):
            x[x<bound] = bound
            return x
        self.addFilter(bndfunc)
        
    def fitDataFixed(self,*args,**kwargs):
        """
        Calls fitData with kwargs and args, but ignores fixedpars 
        argument and uses 'fixedmods' or 'freemods' kwarg to 
        determine which parameters should be fixed
        
        freemods or fixedmods should be a sequence of indecies of 
        models for which the parameters should be left free or held
        fixed
        """
        fps = []
        if 'fixedmods' in kwargs and 'freemods' in kwargs:
            raise TypeError('fitDataFixed cannot have both fixedmod and freemod arguments')
        elif 'fixedmods' in kwargs:
            for i in kwargs.pop('fixedmods'):
                stri = str(i)
                for p in self._models[i].params:
                    fps.append(p+stri)
        elif 'freemods' in kwargs:
            fps.extend(self.params)
            for i in kwargs.pop('freemods'):
                stri=str(i)
                for p in self._models[i].params:
                    fps.remove(p+stri)
                
        else:
            raise TypeError('fitDataFixed must have fixedmods or freemods as arguments')
            
        
        if len(args)>=4:
            args[3] = fps
        else:
            kwargs['fixedpars'] = fps
        return self.fitData(*args,**kwargs)
            
    @property
    def models(self):
        return self._models
    
    @property
    def ops(self):
        return self._ops  
    
class ModelGrid1D(object):
    """
    A set of models that are matching types and represnt a grid of parameter
    values.  The main purpose is to allow the grid to be inverted to extract
    parameter values from the grid
    """
    
    def __init__(self,models,nmodels=None,extraparams={},**params):
        """
        models can be a sequence of models (must be the same type) or a model
        type.  If a type, the number of models to generate will be inferred
        from the parameters (or nmodels if the parameters are all scalar)
        """
        from operator import isSequenceType
        
        n = nmodels
        if isSequenceType(models) and not isinstance(models,basestring):
            for i,m in enumerate(models):
                if not isinstance(m,ParametricModel):
                    raise TypeError('Invalid model given as sequence index %i'%i)
            if n is not None and n != len(models):
                raise ValueError('n does not match the number of models')
            n = len(models)
            modcls= None
        else:
            modcls = get_model(models)
            d = params.copy()
            d.update(extraparams)
            for p,pv in d.iteritems():
                if isSequenceType(pv):
                    nn = len(pv)
                    if n is not None:
                        if n != nn:
                            raise ValueError('param %s does not match previous value'%p)
                    else:
                        n = len(pv)
        if n is None:
            raise ValueError('must specify n if nothing else is a sequence')
                
        if modcls is not None:
            models = [modcls() for i in range(n)]
            
        extraparams = dict([(p,pv) if isSequenceType(pv) else (p,pv*np.ones(n))for p,pv in extraparams.iteritems()])    
        params = dict([(p,pv) if isSequenceType(pv) else (p,pv*np.ones(n))for p,pv in params.iteritems()]) 
        
        for i,m in enumerate(models):
            for p,pv in params.iteritems():
                setattr(m,p,pv[i])
            
        self.models = models
        self.extraparams = extraparams
        
        self.interpmethod = 'lineary'
        
    def getParam(self,x,y,parname):
        """
        computes the value of the requested parameter that interpolates onto
        the provided point
        """        
        isscalar = np.isscalar(x)
        
        x = np.atleast_1d(x)
        y = np.atleast_1d(y)
        if x.shape != y.shape:
            raise ValueError("x and y do not match")
        
        if self.interpmethod == 'lineary':
            modys = np.array([m(x) for m in self.models])
            if parname in self.extraparams:
                ps = self.extraparams[parname]
            else:
                ps = [getattr(m,parname) for m in self.models]
            
            res = np.array([np.interp(y[i],modys[:,i],ps) for i,xi in enumerate(x)])
        elif self.interpmethod == 'linearx':
            raise NotImplementedError('linearx not ready')
        else:
            raise NotImplementedError('invalid interpmethod')
        
        if isscalar:
            return res[0]
        else:
            return res
        
    def plot(self,*args,**kwargs):
        from matplotlib import pyplot as plt
        
        if kwargs.pop('clf',True):
            plt.clf()
        kwargs['clf'] = False
        for m in self.models:
            m.plot(*args,**kwargs)
Grid1DModel = ModelGrid1D #for old modules

class InputCoordinateTransformer(object):
    """
    This mixin (i.e. intnded to be subclassed) class converts 
    FunctionModel input values from one coordinate system to another.
    
    In subclasses, the following should be defined at class level:
    
    * '_inputtransforms': a dictionary of dictionaries where the 
      values are functions that define the transforms as
      _intransforms[incoordsys][funccoordsys] = func
    * 'incoordsys': the default input coordinate system
    * 'fcoordsys': the coordinate system the function is defined in 
    
    to implement the transform, just call tranformCoordinates(input) and 
    feed the return value into the f-function
    """
    _inputtransforms = {}
    incoordsys = None
    _fcoordsys = None
    
    def transformCoordinates(self,x,incoordsys=None,outcoordsys=None):
        """
        transform from the input coordinate system into that defined for 
        the model function
        
        if incoordsys is None, self.incoordsys will be used
        """
        if incoordsys is None:
            incoordsys = self.incoordsys
        if outcoordsys is None:
            outcoordsys = self._fcoordsys
        if incoordsys == outcoordsys:
            return x
        else:
            return self._inputtransforms[incoordsys][outcoordsys](*x)
        
    def addTransform(self,input,output,func):
        """
        add a new transform for this coordinate system with the given 
        input and ouput names and the specified function.  Functions
        are expected to take oen argument - an arrays with at least 2 
        dimensions with the first dimension defining the coordinate system
        """
        import inspect
        from collections import defaultdict
        
        try:
            args, varargs, varkw, defaults = inspect.getargspec(func)
            if len(args)-1 > len(defaults) or varkw:
                raise TypeError('input function must take one argument')
        except TypeError:
            raise TypeError('input func is not a callable')
        
        #make sure we are in the instance
        if '_inputtransforms' not in self.__dict__:
            dd = defaultdict(dict)
            dd.update(self._inputtransforms)
            self._inputtransforms = dd
            
        dd[input][output] = func
            

class FunctionModel2DScalar(FunctionModel,InputCoordinateTransformer):
    """
    This class is a FunctionModel that maps a two-dimensional input to a
    scalar output for each 2D coordinate.  The input thus is at least a 
    two-dimensional array, with the first dimension of length 2.
    """
    from ..coords import cartesian_to_polar,polar_to_cartesian
    
    _inputtransforms = {'cartesian':{'polar':cartesian_to_polar},
                        'polar':{'cartesian':polar_to_cartesian}}
    incoordsys = 'cartesian'
    _fcoordsys = 'cartesian'
    
    def _filterfunc(self,x,*params):
        return self.f(self.transformCoordinates(x),*params)
    
    def __call__(self,x):
        """
        call the function on the input x,which will be flattened.  If not 1D,
        the output will be reshaped to the input
        """
        arr = np.array(x,copy=False,dtype=float)
        
        if len(arr.shape) > 1:
            subshape = arr.shape[1:]
        elif len(arr.shape) == 1:
            subshape = tuple()
        else:
            raise ModelTypeError('Scalar cannot be fed into 2D model')
        
        try:
            arr = arr.reshape(2,np.prod(subshape))
        except ValueError:
            raise ModelTypeError('2D model input must have first dimension of length 2')
        
        return self._filterfunc(arr,*self.parvals).reshape(subshape)
    
    def integrateCircular(self,outr,inr=0,theta=(0,2*pi),**kwargs):
        """
        Integrates the function circularly from inr to outr 
        (default is for inr to be 0)
        
        theta is a tuple of the form (lowertheta,uppertheta)
        
        kwargs are passed into scipy.integrate.dblquad
        """
        import scipy.integrate as itg
        oldcoordsys = self.incoordsys
        try:
            self.incoordsys = 'polar'
            f = lambda th,r:r*self((r,th))
            
            res = itg.dblquad(f,inr,outr,lambda y:theta[0],lambda y:theta[1],**kwargs)
        finally:
            self.incoordsys = oldcoordsys
            
        self.lastintegrate = res
        return res[0]
    
    def integrateCartesian(self,xl,xu,yl,yu,**kwargs):
        """
        Integrates the function in a rectangular area
        bounded to the left by xl, to the right by xu,
        on the bottom by yl, and the top by yu
        
        kwargs are passed into scipy.integrate.dblquad
        """
        import scipy.integrate as itg
        
        oldcoordsys = self.incoordsys
        try:
            self.incoordsys = 'cartesian'
            f = lambda y,x:self((x,y))
            
            res = itg.dblquad(f,xl,xu,lambda y:yl,lambda y:yu,**kwargs)
        finally:
            self.incoordsys = oldcoordsys
            
        self.lastintegrate = res
        return res[0]
    
    def gradient(self,x):
        raise NotImplementedError
    
    def pixelize(self,xl,xu,yl,yu,nx=100,ny=100,sampling=None):
        """
        generates a 2D array of the model covering the range given by
        xl,xu,yl, and yu (same form as `integrateCartesian`), with
        nx horizontal pixels and ny vertical pixels
        
        if sampling is None, each pixel will be computed by integrating the
        model over the area of the pixel, and the resulting array will be set
        to self.lastintegrate and returned
        otherwise, sampling gives the factor to multiply nx and ny by to get
        the total number of "virtual pixels" that will be averaged to get
        the actual result at the given grid point.  If <=1, this is equivalent
        to directly sampling the model.
        """
        import scipy.integrate as itg
        
        oldcoordsys = self.incoordsys
        try:
            self.incoordsys = 'cartesian'        
            
            if sampling is None:
                xs = np.linspace(xl,xu,nx+1)
                xs = np.vstack((xs,np.roll(xs,-1))).T[:-1]
                ys = np.linspace(yl,yu,ny+1)
                ys = np.vstack((ys,np.roll(ys,-1))).T[:-1]
                
                res = np.empty((2,nx,ny))
                f = lambda y,x:self((x,y))
                
                #TODO:optimize more?
                for i,(xl,xu) in enumerate(xs):
                    for j,(yl,yu) in enumerate(ys):
                        res[:,i,j] = itg.dblquad(f,xl,xu,lambda y:yl,lambda y:yu)
                        
                self.lastintegrate = res #res[0]= result, res[1]= integration error
                return res[0]
            else:
                da = ((xu-xl)/nx)*((yu-yl)/ny)
                sampling = int(sampling)
                
                if sampling<=1:
                    xg,yg = np.mgrid[xl:xu:1j*nx,yl:yu:1j*ny]
                    return self((xg,yg))*da
                else:
                    xg,yg = np.mgrid[xl:xu:1j*nx*sampling,yl:yu:1j*ny*sampling]
                    res = self((xg,yg))
                    res = res.reshape((nx*sampling,ny,sampling)).mean(axis=-1)
                    res = res.reshape((nx,sampling,ny)).mean(axis=-2)
                    return res*da
            
        finally:
            self.incoordsys = oldcoordsys
                
    
    def plot(self,datarange=None,nx=100,ny=100,clf=True,cb=True,data='auto',
                  log=False,**kwargs):
        """
        Plots the model over the range requested using the matplotlib 
        imshow function.
        
        datarange should be in the form (xl,xu,yl,yu) or None.  If None, it 
        will be inferred from the data, or a ValueError will be raised
        if data is not present
        
        kwargs are passed into imshow
        """
        from matplotlib import pyplot as plt
        from operator import isMappingType
        
        isinter = plt.isinteractive()
        try:
            plt.ioff()
            if data == 'auto':
                data = self.fitteddata or None
                
            maxmind = None
            if data: #TODO:correct coord conv
                xd,yd = data[0][0],data[0][1]
                dataval = data[1]
                if datarange is None:
                    datarange = (np.min(xd),np.max(xd),np.min(yd),np.max(yd))
                maxmind = (np.max(dataval),np.min(dataval))
            elif datarange is None:
                if self.rangehint is None:
                    raise ValueError("Can't choose limits for plotting without data or a range hint")
                else:
                    datarange = self.rangehint
                
            
            grid = np.mgrid[datarange[0]:datarange[1]:1j*nx,datarange[2]:datarange[3]:1j*ny]
            res = self(grid)
            
            if log:
                res = np.log10(res)
                if data:
                    dataval = np.log10(dataval)
                if maxmind is not None:
                    maxmind = np.log10(maxmind)
            
            if maxmind:
                norm = plt.normalize(min(np.min(res),maxmind[1]),max(np.max(res),maxmind[0]))
            else:
                norm = plt.normalize(np.min(res),np.max(res))
            
            if clf:
                plt.clf()
                
            kwargs.setdefault('aspect','auto')
            plt.imshow(res.T,norm=norm,extent=datarange,**kwargs)
            
            if cb:
                if isMappingType(cb):
                    plt.colorbar(**cb)
                else:
                    plt.colorbar()
            
            if data:
                if isMappingType(data):
                    kwscat = dict(data)
                else:
                    kwscat = {}
                kwscat.setdefault('norm',norm)
                kwscat.setdefault('c',dataval)
                plt.scatter(xd,yd,**kwscat)
                    
            plt.xlim(datarange[0],datarange[1])
            plt.ylim(datarange[2],datarange[3])
            
            if isinter:
                plt.draw()
                plt.show()
        finally:
            plt.interactive(isinter)
    def plot3d(self,datarange=None,nx=100,ny=100,clf=True,cb=True,data='auto',**kwargs):
        """
        Generate a 3D plot of the model using mayavi.
        
        See `plot` function for meaning of the arguments
        
        #TODO:test
        """
        from enthought.mayavi import mlab as M
        from operator import isMappingType
        
        if data == 'auto':
            data = self.fitteddata or None
        
        if data: #TODO:correct coord conv
            xd,yd = data[0][0],data[0][1]
            if datarange is None:
                datarange = (np.min(xd),np.max(xd),np.min(yd),np.max(yd))
            maxmind = (np.max(data[1]),np.min(data[1]))
        elif datarange is None:
            if self.rangehint is None:
                raise ValueError("Can't choose limits for plotting without data or a range hint")
            else:
                datarange = self.rangehint
            maxmind = None
        
        grid = np.mgrid[datarange[0]:datarange[1]:1j*nx,datarange[2]:datarange[3]:1j*ny]
        res = self(grid)
        
#        if maxmind:
#            norm = plt.normalize(min(np.min(res),maxmind[1]),max(np.max(res),maxmind[0]))
#        else:
#            norm = plt.normalize(np.min(res),np.max(res))
        
        if clf:
            plt.clf()
            
        M.mesh(grid[0],grid[1],res)
        
        if cb:
            if isMappingType(cb):
                M.colorbar(**cb)
            else:
                M.colorbar()
        
        if data:
            if isMappingType(data):
                kwscat = dict(data)
            else:
                kwscat = {}
            kwscat.setdefault('norm',norm)
            kwscat.setdefault('c',data[1])
            M.points3d(xd,yd,**kwscat)
                
        #M.xlim(datarange[0],datarange[1])
        #M.ylim(datarange[2],datarange[3])
            
    def plotResiduals(self,x=None,y=None,fmt='or',xaxis='r',clf=True,relative=False):
        """
        Plots residuals between data and the model.  If x and y are None,
        the residuals will be inferred from the last-fit data.
        
        if relative is true, the plot will be relative residuals 
        (e.g. residual/model) instead of the absolute residuals
        
        xaxis can be 'r','theta','x', or 'y'
        """
        from matplotlib import pyplot as plt
        
        isinter = plt.isinteractive()
        try:
            x,y,res = self.residuals(x,y,retdata=True)
            if relative:
                res = res/self(x)
            
            if xaxis=='r':
                outcoordsys = 'polar'
                cind = 0
            elif xaxis=='theta':
                outcoordsys = 'polar'
                cind = 1
            elif xaxis=='x':
                outcoordsys = 'cartesian'
                cind = 0
            elif xaxis=='y':
                outcoordsys = 'cartesian'
                cind = 1
            else:
                raise ValueError('unrecognized x-axis type')
            if clf:
                plt.clf()
            xt = self.transformCoordinates(x,outcoordsys=outcoordsys)[cind]
            plt.plot(xt,res,fmt)
            plt.axhline(0,color='k',ls=':')
            plt.xlabel(xaxis)
            if isinter:
                    plt.draw()
                    plt.show()
        finally:
            plt.interactive(isinter)
    
class FunctionModel2DScalarAuto(FunctionModel2DScalar):
    """
    A `FunctionModel2DScalar` that has its parameters set by the 'f' 
    function following the method of `AutoParamsMeta`
    """
    __metaclass__ = AutoParamsMeta
    
class FunctionModel2DScalarSeperable(FunctionModel2DScalar):
    """
    A `FunctionModel2DScalar` that is seperable and follows a radial and 
    polar function that are just multiples
    """
    def __init__(self,rmodel,thetamodel=None):
        """
        rmodel is the name of a FunctionModel1D that 
        """
        if rmodel is None:
            self.__dict__['_rmodel'] = None
        elif isinstance(rmodel,FunctionModel1D):
            self.__dict__['_rmodel'] = rmodel
        else:
            self.__dict__['_rmodel'] = get_model(rmodel,FunctionModel1D)()
            
        if thetamodel is None:
            self.__dict__['_thetamodel'] = None    
        elif isinstance(thetamodel,FunctionModel1D):
            self.__dict__['_thetamodel'] = thetamodel
        else:
            self.__dict__['_thetamodel'] = get_model(thetamodel,FunctionModel1D)()
            
        self._fixParams()
    
    _fcoordsys = 'polar'
    def f(self,x,*params):
        self.parvals = params
        R = self._rmodel(x[0]) if self._rmodel is not None else 1
        T = self._thetamodel(x[1]) if self._thetamodel is not None else 1
        return R*T
    
    def _gettmod(self):
        return self._thetamodel
    def _settmod(self,val):
        if not (val is None or isinstance(val,FunctionModel1D)):
            raise TypeError('input value is not a FunctionModel1D')
        self._thetamodel = val
        self._fixParams()
        
    def _getrmod(self):
        return self._rmodel
    def _setrmod(self,val):
        if not (val is None or isinstance(val,FunctionModel1D)):
            raise TypeError('input value is not a FunctionModel1D')
        self._rmodel = val
        self._fixParams()
        
    def _fixParams(self):
        ps = list()
        if self._rmodel is not None:
            ps.extend(self._rmodel.params)
        if self._thetamodel is not None:
            ps.extend(self._thetamodel.params)
        self._pars = ps
        
    def __getattr__(self,name):
        if name in self.params:
            if hasattr(self._rmodel,name):
                return getattr(self._rmodel,name)
            elif hasattr(self._thetamodel,name):
                return getattr(self._thetamodel,name)
        else:
            raise AttributeError(name)
        
    def __setattr__(self,name,val):
        if name in self.params:
            if hasattr(self._rmodel,name):
                return setattr(self._rmodel,name,val)
            elif hasattr(self._thetamodel,name):
                return setattr(self._thetamodel,name,val)
        else:
            super(FunctionModel2DScalarSeperable,self).__setattr__(name,val)
            
    @property
    def rangehint(self):
        if self._rmodels is None:
            rh = (1,1)
        else:
            rh = self._rmodel.rangehint
            
        if rh is None:
            return None
        else:
            return -rh[1],rh[1],-rh[1],rh[1] #assume theta is not localized
            
class FunctionModel2DScalarDeformedRadial(FunctionModel2DScalar):
    """
    A `FunctionModel2DScalar` with a profile that is flattened along an axis 
    but has a radial form if unflattened
    
    atob is a ratio of the large to small axis, and pa is the
    position angle measured in radians from the x-axis to the y-axis 
    (e.g. west to north)
    """
    def __init__(self,rmodel,atob=1,pa=0):
        if isinstance(rmodel,FunctionModel1D):
            self.__dict__['_rmodel'] = rmodel
        else:
            self.__dict__['_rmodel'] = get_model(rmodel,FunctionModel1D)()
        self.__dict__['_rmodel'].incoordsys = 'cartesian'
        self._fixPars()
        self.atob = atob
        self.pa = pa
        
    _fcoordsys = 'cartesian'    
    def f(self,arrin,*params):
        #self.parvals = params
        params = list(params)
        pa = params.pop()
        atob = params.pop()
        
        #xr=(-sinpa*x+cospa*y)/cosi
        #yr=(x*cospa+y*sinpa)
        x,y = arrin
        sinpa,cospa = np.sin(pa),np.cos(pa)
        xr=(-sinpa*x+cospa*y)
        yr=(x*cospa+y*sinpa)/atob
        return self._rmodel((xr*xr+yr*yr)**0.5)
        
        
    def _fixPars(self):
        ps = list(self._rmodel.params)
        ps.append('atob')
        ps.append('pa')
        self.__dict__['_pars'] = tuple(ps)
        
    def _getrmodel(self):
        return self._rmodel
    def _setrmodel(self,val):
        if not isinstance(val,FunctionModel1D):
            raise TypeError('input value is not a FunctionModel1D')
        self._rmodel = val
        self._rmodel.incoordsys = 'cartesian'
        self._fixPars()
        
    def __getattr__(self,name):
        if hasattr(self._rmodel,name):
            return getattr(self._rmodel,name)
        else:
            raise AttributeError(name)
        
    def __setattr__(self,name,val):
        if hasattr(self._rmodel,name):
            return setattr(self._rmodel,name,val)
        else:
            super(FunctionModel2DScalarDeformedRadial,self).__setattr__(name,val)
            
    def _getPaDeg(self):
        np.degrees(self.pa)
    def _setPaDeg(self,val):
        self.pa = np.radians(val)     
    padeg=property(_getPaDeg,_setPaDeg,"""position angle (from +x-axis
            to +y-axis) in degrees
            """)
    
    def _getInc(self):
        return np.arccos(1/self.atob)
    def _setInc(self,val):
        self.atob = 1/np.cos(val)
    inc=property(_getInc,_setInc,doc="""
        inclination angle of object in radians - maps onto atob
        """)
        
    def _getIncDeg(self):
        return np.degrees(np.arccos(1/self.atob))
    def _setIncDeg(self,val):
        self.atob = 1/np.cos(np.radians(val))
    incdeg=property(_getIncDeg,_setIncDeg,doc="""
        inclination angle of object in degrees - maps onto atob
        """)
            
    @property
    def rangehint(self):
        rh = self._rmodel.rangehint
        if rh is None:
            return None
        else:
            return -rh[1],rh[1],-rh[1],rh[1] #assume theta is not localized
        
#<-------------------------------Module functions ----------------------------->  
__model_registry={}
def register_model(model,name=None,overwrite=False,stripmodel=True):
    """
    register a model at the module package level for get_model and list_model
    
    model is the class object
    
    name is the name to assign (class name will be used if this is None)
    
    if overwrite is True, if a model already exists with the provided name, it
    will be silently overwritten, otherwise a KeyError will be raised
    
    if stripmodel is true, the characters 'model' will be stripped from
    the name before the model is assigned
    """
    if not issubclass(model,ParametricModel):
        raise TypeError('Supplied model is not a Model')
    if name is None:
        name = model.__name__.lower()
    else:
        name = name.lower()
    if stripmodel:
        name = name.replace('model','')
    if overwrite and name in __model_registry:
        raise KeyError('Model %s already exists'%name)
    
    __model_registry[name]=model
    
def get_model(model,baseclass=None):
    """
    returns the class object for the requested model in the model registry
    
    the model can be a name, instance, or class object
    
    if baseclass is not None, it can specify that the requested model 
    me a subclass of the provided base class.  If not, a TypeError
    will be raised.
    
    KeyError is raise if a name is provided and it is incorrect, all other 
    invalid inputs raise a TypeError
    """
    from inspect import isclass
    
    if isinstance(model,basestring):    
        res = __model_registry[model]
    elif isclass(model):
        if issubclass(model,ParametricModel):
            res = model
        else:
            raise TypeError('class object is not a Model')
    elif issubclass(model.__class__,ParametricModel):
        res = model.__class__
    else:
        raise TypeError('attempted to get invalid model')
    
    if baseclass:
        if not issubclass(res,baseclass):
            raise TypeError('%s is not a subclass of %s'%(res,baseclass))
        
    return res

#TODO:fix ndims
def list_models(include=None,exclude=None,baseclass=None):
    """
    lists the registered model objects in the package
    
    include is a sequence of model names to include in the list (e.g. the 
    function will just validate that they are valid models and return the
    strings) - if not in the registry, a ValueError will be raised
    
    exclude is a sequence of model names that should be excluded (if any 
    are not in the registry, a ValueError will be raised)
    
    providing a class to the baseclass argument will filter out all models that
    are not subclasses of the provided class.  
    """
    from operator import isSequenceType
    
    if baseclass is not None:
        res = [k for k,c in __model_registry.iteritems() if issubclass(c,baseclass)]
    else:
        res = __model_registry.keys()
        
    if include is not None:
        if exclude is not None:
            raise TypeError("can't specify both included models and excluded models")
        if isinstance(include,basestring) or not isSequenceType(include):
            include = [include]
        for m in include:
            if m not in res:
                raise ValueError('modelname to include %s not a valid model name'%m)
            res = include
    elif exclude is not None:
        if isinstance(exclude,basestring) or not isSequenceType(exclude):
            exclude = [exclude]
        for m in exclude:
            if m not in res:
                raise ValueError('modelname to exclude %s not a valid model name'%m)
            res.remove(m)
    
    return res


def intersect_models(m1,m2,bounds=None,nsample=1024,full_output=False,**kwargs):
    """
    determine the points where two models intersect
    
    if bounds is None, the bounds will be determined from the model data if
    any is saved.  Otherwise, it should be (min,max) for the region to look
    for points
    
    returns a sorted array of points where the two models intersect on the 
    interval (up to a resolution in nsample), or if full_output is True,
    returns array,scipy.optimize.zeros.RootResults
    
    kwargs are passed into scipy.optimize.brentq
    """
    from scipy.optimize import brentq
    
    if bounds is None:
        data1 = m1.fitteddata if hasattr(m1,'fitteddata') else None
        data2 = m2.fitteddata if hasattr(m2,'fitteddata') else None
        
        if data1 is None and data2 is None:
            raise ValueError('must supply bounds if neither model has data')
        elif data1 is None:
            data2 = data2[0]
            bounds = (np.min(data2),np.max(data2))
        elif data2 is None:
            data1 = data1[0]
            bounds = (np.min(data1),np.max(data1))
        else: #both are valid
            data1 = data1[0]
            data2 = data2[0]
            bounds = (min(np.min(data1),np.min(data2)),max(np.max(data1),np.max(data2)))
    
    xsample = np.linspace(bounds[0],bounds[1],nsample)
    
    diff = m1(xsample) - m2(xsample)
    transis = np.convolve(diff>0,[1,-1]) #1-> crossing up between index and the one before
    transis[0] = 0
    transis[-1] = 0
    
    inters = []
    reses = []
    kwargs['full_output'] = 1
    for i in np.where(transis)[0]:
        t = brentq(lambda x:m1(x)-m2(x),xsample[i-1],xsample[i],**kwargs)
        inters.append(t[0])
        reses.append(t[1])
        
    arr = np.array(inters)
    arr.sort()
    
    if full_output:
        return arr,reses
    else:
        return arr
    
def offset_model(model,pname='C',**kwargs):
    """
    generator function that takes a Model type (class or name) and uses it
    to construct a CompositeModel with an extra parameter that is a constant
    offset (with a name given by the pname argument)
    
    kwargs are used to set the parameter values
    """
    from .modbuiltins import ConstantModel
    
    return CompositeModel1D((model,ConstantModel),('+'),{'C1':pname},**kwargs)
    
def scale_model(model,pname='A',**kwargs):
    """
    generator function that takes a Model type (class or name) and uses it
    to construct a CompositeModel with an extra parameter that is a constant
    offset (with a name given by the pname argument)
    
    kwargs are used to set the parameter values
    """
    from .modbuiltins import ConstantModel
    
    mod = CompositeModel1D((model,ConstantModel),('*'),{'C1':pname},**kwargs)

    if pname not in kwargs:
        setattr(mod,pname,1.0)
    return mod

def scale_and_offset_model(model,scalepname='A',offsetpname='C',**kwargs):
    """
    generator function that takes a Model type (class or name) and uses it
    to construct a CompositeModel that adds a 'C1' parameter that scales the
    model, and a 'C2' parameter than is the offset
    
    kwargs are used to set the parameters
    """
    from .modbuiltins import ConstantModel
    
    mod = CompositeModel1D((model,ConstantModel,ConstantModel),('*','+'),{'C1':scalepname,'C2':offsetpname},**kwargs)
    if scalepname not in kwargs:
        setattr(mod,scalepname,1.0)
    return mod
    
    
def binned_weights(values,n,log=False):
    """
    Produces an array of values of the same size as values that is generated
    by subdividing the values into n bins such that each bin has an equal share
    of the total number of values.
    
    Returns an array of values on [0,1]
    
    if log is True, the values are evenly-spaced on logarithmic intervals
    """
    
    if log:
        values = np.log(values).ravel()
    else:
        values = np.array(values,copy=False).ravel()
        
    mx,mi = np.max(values),np.min(values)
    
    n,edges = np.histogram(values)
    ws = np.zeros_like(values)
    
    wsr = ws.ravel()
    for i,w in enumerate(1.0/n):
        m = (edges[i]<=values) & (values<edges[i+1])
        wsr[m] = w 
    wsr[edges[-1]==values] = w
    
    return ws